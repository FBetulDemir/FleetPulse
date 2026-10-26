"""Decides when alerts open and resolve. No database or MQTT code lives here.

Three kinds of alerts:
- threshold: a reading crosses a rule's threshold (e.g. battery below 20 %)
- offline: the device disconnected (MQTT Last Will), or stopped sending telemetry
- invalid_telemetry: the device sent a message that failed validation
"""

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from fleetpulse_backend.db.models import ComparisonOperator
from fleetpulse_backend.metrics import UNITS, Metric
from fleetpulse_contracts import ConnectionState, StatusMessage, TelemetryMessage
from fleetpulse_contracts.alerts import AlertEvent, AlertMessage, AlertSeverity, AlertType

logger = logging.getLogger("fleetpulse.alerts")

OFFLINE_AFTER = timedelta(seconds=60)


@dataclass(frozen=True)
class Rule:
    id: uuid.UUID
    name: str
    vessel_uuid: uuid.UUID | None  # None: applies to every vessel
    metric: Metric
    operator: ComparisonOperator
    threshold: float
    severity: AlertSeverity


@dataclass(frozen=True)
class AlertKey:
    """Identifies "the same" alert: one may be open per key at a time."""

    vessel_uuid: uuid.UUID
    alert_type: AlertType
    rule_id: uuid.UUID | None = None


@dataclass(frozen=True)
class NewAlert:
    key: AlertKey
    vessel_id: str
    severity: AlertSeverity
    message: str
    value: float | None
    at: datetime


class AlertStorage(Protocol):
    async def open(self, alert: NewAlert) -> AlertMessage | None:
        """Stores the alert, or returns None if one with the same key is already open."""
        ...

    async def resolve(self, key: AlertKey, vessel_id: str, at: datetime) -> AlertMessage | None:
        """Resolves the open alert with this key, if there is one."""
        ...


Publish = Callable[[AlertEvent], Awaitable[None]]


def hysteresis(threshold: float) -> float:
    """How far a value must move back past the threshold before the alert resolves.

    Without it, a value hovering around the threshold would open and resolve an alert
    on every reading.
    """
    return max(abs(threshold) * 0.05, 0.5)


def breaches(rule: Rule, value: float) -> bool:
    if rule.operator is ComparisonOperator.ABOVE:
        return value > rule.threshold
    return value < rule.threshold


def clears(rule: Rule, value: float) -> bool:
    margin = hysteresis(rule.threshold)
    if rule.operator is ComparisonOperator.ABOVE:
        return value <= rule.threshold - margin
    return value >= rule.threshold + margin


def threshold_message(rule: Rule, value: float) -> str:
    unit = UNITS[rule.metric]
    side = "above" if rule.operator is ComparisonOperator.ABOVE else "below"
    return f"{rule.name}: {value:.1f} {unit} ({side} {rule.threshold:g} {unit})"


class AlertEngine:
    def __init__(
        self, storage: AlertStorage, publish: Publish, offline_after: timedelta = OFFLINE_AFTER
    ) -> None:
        self._storage = storage
        self._publish = publish
        self._offline_after = offline_after
        self._rules: list[Rule] = []
        self._vessels: dict[str, uuid.UUID] = {}
        self._open: set[AlertKey] = set()
        self._last_seen: dict[str, datetime] = {}

    def load(
        self, rules: list[Rule], vessels: dict[str, uuid.UUID], open_alerts: set[AlertKey]
    ) -> None:
        """Replaces rules and the vessel registry; called at startup and periodically."""
        self._rules = rules
        self._vessels = vessels
        self._open = set(open_alerts)

    async def on_telemetry(self, reading: TelemetryMessage, now: datetime) -> None:
        vessel_uuid = self._vessels.get(reading.vessel_id)
        if vessel_uuid is None:
            return  # unregistered vessels have no alerts
        self._last_seen[reading.vessel_id] = now

        # A valid reading means the device is back and sending good data.
        await self._resolve(AlertKey(vessel_uuid, AlertType.OFFLINE), reading.vessel_id, now)
        await self._resolve(
            AlertKey(vessel_uuid, AlertType.INVALID_TELEMETRY), reading.vessel_id, now
        )

        for rule in self._rules:
            if rule.vessel_uuid not in (None, vessel_uuid):
                continue
            value = float(getattr(reading, rule.metric.value))
            key = AlertKey(vessel_uuid, AlertType.THRESHOLD, rule.id)
            if key not in self._open and breaches(rule, value):
                message = threshold_message(rule, value)
                await self._open_alert(
                    NewAlert(key, reading.vessel_id, rule.severity, message, value, now)
                )
            elif key in self._open and clears(rule, value):
                await self._resolve(key, reading.vessel_id, now)

    async def on_status(self, status: StatusMessage, now: datetime) -> None:
        vessel_uuid = self._vessels.get(status.vessel_id)
        if vessel_uuid is None or status.state is not ConnectionState.OFFLINE:
            # Coming online alone does not resolve "offline": data must flow again.
            return
        self._last_seen.pop(status.vessel_id, None)
        await self._open_offline(vessel_uuid, status.vessel_id, "Device disconnected", now)

    async def on_invalid(self, vessel_id: str | None, reason: str, now: datetime) -> None:
        vessel_uuid = self._vessels.get(vessel_id) if vessel_id else None
        if vessel_uuid is None or vessel_id is None:
            return
        key = AlertKey(vessel_uuid, AlertType.INVALID_TELEMETRY)
        if key not in self._open:
            message = f"Invalid telemetry: {reason}"[:200]
            await self._open_alert(
                NewAlert(key, vessel_id, AlertSeverity.WARNING, message, None, now)
            )

    async def sweep(self, now: datetime) -> None:
        """Opens offline alerts for connected devices that have gone silent."""
        for vessel_id, seen in list(self._last_seen.items()):
            vessel_uuid = self._vessels.get(vessel_id)
            if vessel_uuid is not None and now - seen > self._offline_after:
                seconds = int(self._offline_after.total_seconds())
                await self._open_offline(
                    vessel_uuid, vessel_id, f"No telemetry for {seconds} s", now
                )

    async def _open_offline(
        self, vessel_uuid: uuid.UUID, vessel_id: str, message: str, now: datetime
    ) -> None:
        key = AlertKey(vessel_uuid, AlertType.OFFLINE)
        if key not in self._open:
            await self._open_alert(
                NewAlert(key, vessel_id, AlertSeverity.CRITICAL, message, None, now)
            )

    async def _open_alert(self, alert: NewAlert) -> None:
        self._open.add(alert.key)
        stored = await self._storage.open(alert)
        # None: the database already had this alert open (e.g. after a worker restart).
        if stored is not None:
            logger.info("alert opened for %s: %s", alert.vessel_id, alert.message)
            await self._publish(AlertEvent(event="created", alert=stored))

    async def _resolve(self, key: AlertKey, vessel_id: str, now: datetime) -> None:
        if key not in self._open:
            return
        self._open.discard(key)
        resolved = await self._storage.resolve(key, vessel_id, now)
        if resolved is not None:
            logger.info("alert resolved for %s: %s", vessel_id, resolved.message)
            await self._publish(AlertEvent(event="resolved", alert=resolved))
