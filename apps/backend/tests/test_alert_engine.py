import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from fleetpulse_backend.alerts.engine import AlertEngine, AlertKey, NewAlert, Rule, hysteresis
from fleetpulse_backend.db.models import ComparisonOperator
from fleetpulse_backend.metrics import Metric
from fleetpulse_contracts import ConnectionState, StatusMessage, TelemetryMessage
from fleetpulse_contracts.alerts import (
    AlertEvent,
    AlertMessage,
    AlertSeverity,
    AlertStatus,
    AlertType,
)

T0 = datetime(2026, 10, 26, 10, 0, tzinfo=UTC)
VESSEL = uuid.uuid4()
OTHER_VESSEL = uuid.uuid4()
VESSELS = {"vessel-001": VESSEL, "vessel-002": OTHER_VESSEL}

LOW_BATTERY = Rule(
    uuid.uuid4(), "Low battery", None, Metric.BATTERY_PERCENT, ComparisonOperator.BELOW, 20.0,
    AlertSeverity.WARNING,
)  # fmt: skip
HOT_MOTOR = Rule(
    uuid.uuid4(), "High motor temperature", None, Metric.MOTOR_TEMPERATURE_C,
    ComparisonOperator.ABOVE, 70.0, AlertSeverity.CRITICAL,
)  # fmt: skip


class FakeStorage:
    """Behaves like the database: at most one open alert per key."""

    def __init__(self) -> None:
        self.open_alerts: dict[AlertKey, AlertMessage] = {}
        self.calls = 0

    async def open(self, alert: NewAlert) -> AlertMessage | None:
        self.calls += 1
        if alert.key in self.open_alerts:
            return None
        message = AlertMessage(
            id=uuid.uuid4(),
            vessel_id=alert.vessel_id,
            alert_type=alert.key.alert_type,
            severity=alert.severity,
            status=AlertStatus.ACTIVE,
            message=alert.message,
            value=alert.value,
            triggered_at=alert.at,
        )
        self.open_alerts[alert.key] = message
        return message

    async def resolve(self, key: AlertKey, vessel_id: str, at: datetime) -> AlertMessage | None:
        self.calls += 1
        message = self.open_alerts.pop(key, None)
        if message is None:
            return None
        return message.model_copy(update={"status": AlertStatus.RESOLVED, "resolved_at": at})


class Harness:
    def __init__(self, rules: list[Rule], open_alerts: set[AlertKey] | None = None) -> None:
        self.storage = FakeStorage()
        self.events: list[AlertEvent] = []
        self.engine = AlertEngine(self.storage, self.publish)
        self.engine.load(rules, VESSELS, open_alerts or set())

    async def publish(self, event: AlertEvent) -> None:
        self.events.append(event)

    def summary(self) -> list[tuple[str, str]]:
        return [(e.event, e.alert.message) for e in self.events]

    async def reading(
        self, seconds: float = 0, vessel_id: str = "vessel-001", **values: Any
    ) -> None:
        fields: dict[str, Any] = {
            "latitude": 57.7, "longitude": 11.9, "speed_knots": 8.0, "course_degrees": 90.0,
            "battery_percent": 80.0, "battery_voltage": 25.0, "motor_temperature_c": 45.0,
            "ambient_temperature_c": 12.0, "status": "underway",
        }  # fmt: skip
        at = T0 + timedelta(seconds=seconds)
        message = TelemetryMessage(
            vessel_id=vessel_id,
            device_id="device-x",
            timestamp=at,
            **{**fields, **values},
        )
        await self.engine.on_telemetry(message, at)


# Thresholds


async def test_breach_opens_one_alert_while_the_value_stays_bad() -> None:
    h = Harness([LOW_BATTERY])

    for second, battery in enumerate([25, 19, 18, 17]):
        await h.reading(second, battery_percent=battery)

    assert h.summary() == [("created", "Low battery: 19.0 % (below 20 %)")]
    assert h.events[0].alert.value == 19
    assert h.events[0].alert.severity is AlertSeverity.WARNING


async def test_below_rule_resolves_only_past_the_hysteresis_margin() -> None:
    h = Harness([LOW_BATTERY])  # margin for 20 is max(5 %, 0.5) = 1.0

    await h.reading(0, battery_percent=19)
    await h.reading(1, battery_percent=20.5)  # back above 20, but within the margin
    await h.reading(2, battery_percent=19.5)  # dips again: still one alert
    assert [e.event for e in h.events] == ["created"]

    await h.reading(3, battery_percent=21)
    assert [e.event for e in h.events] == ["created", "resolved"]
    assert h.events[1].alert.resolved_at == T0 + timedelta(seconds=3)


async def test_above_rule_resolves_only_past_the_hysteresis_margin() -> None:
    h = Harness([HOT_MOTOR])  # margin for 70 is 3.5

    await h.reading(0, motor_temperature_c=75)
    await h.reading(1, motor_temperature_c=68)
    await h.reading(2, motor_temperature_c=66)

    assert [e.event for e in h.events] == ["created", "resolved"]


async def test_vessel_specific_rules_only_apply_to_that_vessel() -> None:
    only_other = Rule(
        uuid.uuid4(), "Slow", OTHER_VESSEL, Metric.SPEED_KNOTS, ComparisonOperator.BELOW, 5.0,
        AlertSeverity.INFO,
    )  # fmt: skip
    h = Harness([only_other])

    await h.reading(0, "vessel-001", speed_knots=1)
    await h.reading(0, "vessel-002", speed_knots=1)

    assert [e.alert.vessel_id for e in h.events] == ["vessel-002"]


async def test_unregistered_vessels_never_alert() -> None:
    h = Harness([LOW_BATTERY])

    await h.reading(0, "vessel-999", battery_percent=1)

    assert h.events == []


async def test_alerts_open_before_a_restart_are_not_duplicated() -> None:
    key = AlertKey(VESSEL, AlertType.THRESHOLD, LOW_BATTERY.id)
    h = Harness([LOW_BATTERY], open_alerts={key})

    await h.reading(0, battery_percent=5)

    assert h.events == []
    assert h.storage.calls == 0  # known to be open: no database round trip


# Offline


async def test_disconnect_opens_an_offline_alert_until_data_flows_again() -> None:
    h = Harness([])
    offline = StatusMessage(
        vessel_id="vessel-001", device_id="device-001", state=ConnectionState.OFFLINE
    )
    online = offline.model_copy(update={"state": ConnectionState.ONLINE})

    await h.engine.on_status(offline, T0)
    await h.engine.on_status(online, T0 + timedelta(seconds=5))
    assert h.summary() == [("created", "Device disconnected")]
    assert h.events[0].alert.severity is AlertSeverity.CRITICAL

    await h.reading(6)
    assert [e.event for e in h.events] == ["created", "resolved"]


async def test_silent_vessel_goes_offline_after_a_minute() -> None:
    h = Harness([])
    await h.reading(0)

    await h.engine.sweep(T0 + timedelta(seconds=59))
    assert h.events == []

    await h.engine.sweep(T0 + timedelta(seconds=61))
    await h.engine.sweep(T0 + timedelta(seconds=70))
    assert h.summary() == [("created", "No telemetry for 60 s")]


# Invalid telemetry


async def test_invalid_messages_alert_until_a_valid_one_arrives() -> None:
    h = Harness([])

    await h.engine.on_invalid("vessel-001", "schema validation failed: 1 errors", T0)
    await h.engine.on_invalid("vessel-001", "schema validation failed: 2 errors", T0)
    await h.engine.on_invalid(None, "unknown topic", T0)
    assert h.summary() == [("created", "Invalid telemetry: schema validation failed: 1 errors")]

    await h.reading(1)
    assert [e.event for e in h.events] == ["created", "resolved"]


@pytest.mark.parametrize(("threshold", "margin"), [(20.0, 1.0), (70.0, 3.5), (5.0, 0.5)])
def test_hysteresis_margin(threshold: float, margin: float) -> None:
    assert hysteresis(threshold) == margin
