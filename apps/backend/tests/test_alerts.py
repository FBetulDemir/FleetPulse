import json
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

from fleetpulse_backend.alerts.engine import AlertKey, NewAlert
from fleetpulse_backend.alerts.store import AlertStore
from fleetpulse_backend.api.relay import to_event
from fleetpulse_backend.db.models import Role, Vessel, VesselType
from fleetpulse_backend.db.seed import DEFAULT_RULES, seed
from fleetpulse_contracts.alerts import AlertEvent, AlertSeverity, AlertType
from fleetpulse_contracts.topics import ALERTS_TOPIC

from .conftest import DbClient, RecordingPublisher, Sessionmaker, make_db_client

T0 = datetime(2026, 10, 26, 10, 0, tzinfo=UTC)
URL = "/api/v1/alerts"


class AlertsDb:
    """Logged-in client plus a vessel and direct access to the alert store."""

    def __init__(self, db: DbClient, publisher: RecordingPublisher) -> None:
        self.db = db
        self.client = db.client
        self.publisher = publisher
        self.vessel_uuid = uuid.uuid4()
        db.run(self._add_vessel)

    async def _add_vessel(self, sessionmaker: Sessionmaker) -> None:
        async with sessionmaker() as session, session.begin():
            session.add(
                Vessel(
                    id=self.vessel_uuid,
                    identifier="vessel-001",
                    name="Vinga Pilot",
                    vessel_type=VesselType.PILOT,
                    length_m=16.8,
                )
            )

    def store(self) -> AlertStore:
        return AlertStore(self.db.sessionmaker)

    def open(
        self,
        alert_type: AlertType = AlertType.OFFLINE,
        severity: AlertSeverity = AlertSeverity.CRITICAL,
        minutes: int = 0,
        rule_id: uuid.UUID | None = None,
    ) -> str | None:
        alert = NewAlert(
            AlertKey(self.vessel_uuid, alert_type, rule_id),
            "vessel-001",
            severity,
            f"{alert_type.value} alert",
            None,
            T0 + timedelta(minutes=minutes),
        )
        stored = self.db.run(lambda _: self.store().open(alert))
        return str(stored.id) if stored else None

    def resolve(self, alert_type: AlertType = AlertType.OFFLINE) -> None:
        key = AlertKey(self.vessel_uuid, alert_type)
        self.db.run(lambda _: self.store().resolve(key, "vessel-001", T0 + timedelta(hours=1)))


@pytest.fixture
def alerts(database_url: str) -> Iterator[AlertsDb]:
    publisher = RecordingPublisher()
    with make_db_client(database_url, publisher) as db:
        yield AlertsDb(db, publisher)


# Storage: the database enforces one open alert per key


def test_only_one_alert_per_key_can_be_open(alerts: AlertsDb) -> None:
    assert alerts.open() is not None
    # Rule-less alerts too: the unique index treats NULL rule ids as equal.
    assert alerts.open() is None


def test_a_new_alert_can_open_after_the_previous_one_resolved(alerts: AlertsDb) -> None:
    first = alerts.open()
    alerts.resolve()

    second = alerts.open()

    assert second is not None and second != first


def test_different_types_can_be_open_at_the_same_time(alerts: AlertsDb) -> None:
    assert alerts.open(AlertType.OFFLINE) is not None
    assert alerts.open(AlertType.INVALID_TELEMETRY) is not None


# API


def test_alerts_require_login(alerts: AlertsDb) -> None:
    assert alerts.client.get(URL).status_code == 401


def test_lists_alerts_newest_first_with_vessel_details(alerts: AlertsDb) -> None:
    alerts.db.login_as(Role.VIEWER)
    alerts.open(AlertType.OFFLINE, minutes=0)
    alerts.open(AlertType.INVALID_TELEMETRY, AlertSeverity.WARNING, minutes=5)

    body = alerts.client.get(URL).json()

    assert body["total"] == 2
    assert [a["alert_type"] for a in body["items"]] == ["invalid_telemetry", "offline"]
    assert body["items"][0]["vessel_name"] == "Vinga Pilot"
    assert body["items"][0]["vessel_identifier"] == "vessel-001"


def test_filters_by_status_and_severity(alerts: AlertsDb) -> None:
    alerts.db.login_as(Role.VIEWER)
    alerts.open(AlertType.OFFLINE)
    alerts.open(AlertType.INVALID_TELEMETRY, AlertSeverity.WARNING)
    alerts.resolve(AlertType.OFFLINE)

    def types(**params: str) -> list[str]:
        return [a["alert_type"] for a in alerts.client.get(URL, params=params).json()["items"]]

    assert types(status="open") == ["invalid_telemetry"]
    assert types(status="resolved") == ["offline"]
    assert types(severity="warning") == ["invalid_telemetry"]


def test_operator_acknowledges_an_alert(alerts: AlertsDb) -> None:
    alerts.db.login_as(Role.OPERATOR)
    alert_id = alerts.open()

    response = alerts.client.post(f"{URL}/{alert_id}/acknowledge")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "acknowledged"
    assert body["acknowledged_by"] == "Operator"
    assert body["acknowledged_at"] is not None
    # Every connected browser learns about it through the alerts topic.
    assert [(e.event, str(e.alert.id)) for e in alerts.publisher.events] == [
        ("acknowledged", alert_id)
    ]


def test_acknowledging_twice_is_harmless(alerts: AlertsDb) -> None:
    alerts.db.login_as(Role.OPERATOR)
    alert_id = alerts.open()
    alerts.client.post(f"{URL}/{alert_id}/acknowledge")

    response = alerts.client.post(f"{URL}/{alert_id}/acknowledge")

    assert response.status_code == 200
    assert len(alerts.publisher.events) == 1


def test_an_acknowledged_alert_still_blocks_duplicates(alerts: AlertsDb) -> None:
    alerts.db.login_as(Role.OPERATOR)
    alerts.client.post(f"{URL}/{alerts.open()}/acknowledge")

    # The condition is still there, so the worker must not open a second alert.
    assert alerts.open() is None


def test_resolved_alerts_cannot_be_acknowledged(alerts: AlertsDb) -> None:
    alerts.db.login_as(Role.OPERATOR)
    alert_id = alerts.open()
    alerts.resolve()

    assert alerts.client.post(f"{URL}/{alert_id}/acknowledge").status_code == 409


def test_viewers_cannot_acknowledge(alerts: AlertsDb) -> None:
    alerts.db.login_as(Role.VIEWER)

    assert alerts.client.post(f"{URL}/{alerts.open()}/acknowledge").status_code == 403


def test_unknown_alert_is_404(alerts: AlertsDb) -> None:
    alerts.db.login_as(Role.ADMIN)

    assert alerts.client.post(f"{URL}/{uuid.uuid4()}/acknowledge").status_code == 404


def test_lists_the_seeded_alert_rules(alerts: AlertsDb) -> None:
    alerts.db.login_as(Role.VIEWER)
    alerts.db.run(lambda sessionmaker: seed(sessionmaker, "demo password"))
    alerts.db.run(lambda sessionmaker: seed(sessionmaker, "demo password"))  # idempotent

    rules = alerts.client.get("/api/v1/alert-rules").json()

    assert sorted(r["name"] for r in rules) == sorted(name for name, *_ in DEFAULT_RULES)


def test_relay_forwards_alert_events_to_websocket_clients() -> None:
    event = AlertEvent.model_validate(
        {
            "event": "created",
            "alert": {
                "id": str(uuid.uuid4()),
                "vessel_id": "vessel-001",
                "alert_type": "offline",
                "severity": "critical",
                "status": "active",
                "message": "Device disconnected",
                "triggered_at": T0.isoformat(),
            },
        }
    )

    result = to_event(ALERTS_TOPIC, event.model_dump_json().encode())

    assert result is not None
    vessel_id, forwarded = result
    assert vessel_id == "vessel-001"
    assert forwarded["type"] == "alert"
    assert forwarded["vessel_id"] == "vessel-001"  # same routing field as other live events
    assert forwarded["event"] == "created"
    assert json.dumps(forwarded)  # serialisable for the WebSocket
