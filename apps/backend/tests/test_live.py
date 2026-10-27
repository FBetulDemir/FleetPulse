import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession
from starlette.websockets import WebSocketDisconnect

from fleetpulse_backend.api.hub import LiveHub
from fleetpulse_backend.api.relay import to_event
from fleetpulse_backend.db.models import Role

from .conftest import DbClient


def telemetry_event(vessel_id: str) -> dict[str, Any]:
    return {"type": "telemetry", "vessel_id": vessel_id, "data": {"speed_knots": 5.0}}


@pytest.fixture
def client(db_client: DbClient) -> Iterator[TestClient]:
    """A client logged in as a viewer; the WebSocket requires login."""
    db_client.login_as(Role.VIEWER)
    yield db_client.client


def close_code(client: TestClient, **headers: str) -> int:
    with (
        pytest.raises(WebSocketDisconnect) as closed,
        client.websocket_connect("/ws", headers=headers) as ws,
    ):
        ws.receive_json()
    return closed.value.code


def test_websocket_requires_login(db_client: DbClient) -> None:
    assert close_code(db_client.client) == 4401


def test_websocket_rejects_other_origins(client: TestClient) -> None:
    assert close_code(client, origin="https://evil.example") == 4403


def test_websocket_accepts_same_origin(client: TestClient) -> None:
    with client.websocket_connect("/ws", headers={"origin": "http://testserver"}) as ws:
        subscribe(ws, channel="fleet")


def publish(client: TestClient, vessel_id: str, event: dict[str, Any]) -> None:
    hub: LiveHub = client.app.state.hub  # type: ignore[attr-defined]
    # Run on the app's event loop, where the subscriber queues live.
    assert client.portal is not None
    client.portal.call(hub.publish, vessel_id, event)


def subscribe(ws: WebSocketTestSession, **message: str) -> None:
    ws.send_json({"type": "subscribe", **message})
    assert ws.receive_json()["type"] == "subscribed"


def test_health(client: TestClient) -> None:
    response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_vessel_subscriber_only_receives_that_vessel(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        subscribe(ws, channel="vessel", vessel_id="vessel-002")

        publish(client, "vessel-001", telemetry_event("vessel-001"))
        publish(client, "vessel-002", telemetry_event("vessel-002"))

        assert ws.receive_json() == telemetry_event("vessel-002")


def test_fleet_subscriber_receives_every_vessel(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        subscribe(ws, channel="fleet")

        publish(client, "vessel-001", telemetry_event("vessel-001"))
        publish(client, "vessel-002", telemetry_event("vessel-002"))

        assert ws.receive_json()["vessel_id"] == "vessel-001"
        assert ws.receive_json()["vessel_id"] == "vessel-002"


def test_alerts_subscriber_receives_only_alerts(client: TestClient) -> None:
    alert = {"type": "alert", "vessel_id": "vessel-001", "event": "created", "alert": {}}
    with client.websocket_connect("/ws") as ws:
        subscribe(ws, channel="alerts")

        publish(client, "vessel-001", telemetry_event("vessel-001"))
        publish(client, "vessel-001", alert)

        assert ws.receive_json() == alert


def test_new_subscriber_gets_latest_state_first(client: TestClient) -> None:
    status = {"type": "vessel_status", "vessel_id": "vessel-003", "state": "offline"}
    publish(client, "vessel-003", status)
    publish(client, "vessel-003", telemetry_event("vessel-003"))

    with client.websocket_connect("/ws") as ws:
        subscribe(ws, channel="vessel", vessel_id="vessel-003")

        assert ws.receive_json() == status
        assert ws.receive_json() == telemetry_event("vessel-003")


@pytest.mark.parametrize(
    "message",
    [
        {"type": "subscribe", "channel": "vessel"},
        {"type": "subscribe", "channel": "fleet", "vessel_id": "vessel-001"},
        {"type": "dance", "channel": "fleet"},
    ],
)
def test_invalid_subscription_returns_error(client: TestClient, message: dict[str, Any]) -> None:
    with client.websocket_connect("/ws") as ws:
        ws.send_json(message)

        assert ws.receive_json()["type"] == "error"


def test_slow_subscriber_drops_oldest_events() -> None:
    hub = LiveHub(max_queued_per_subscriber=2)
    subscriber = hub.connect()
    subscriber.channels.add("fleet")

    for n in range(3):
        hub.publish(f"vessel-00{n}", telemetry_event(f"vessel-00{n}"))

    queued = [subscriber.queue.get_nowait()["vessel_id"] for _ in range(2)]
    assert queued == ["vessel-001", "vessel-002"]


def test_relay_converts_mqtt_messages_to_events() -> None:
    status = json.dumps({"vessel_id": "vessel-001", "device_id": "device-001", "state": "online"})

    assert to_event("fleetpulse/v1/vessels/vessel-001/status", status.encode()) == (
        "vessel-001",
        {"type": "vessel_status", "vessel_id": "vessel-001", "state": "online"},
    )
    assert to_event("fleetpulse/v1/vessels/vessel-002/status", status.encode()) is None
    assert to_event("fleetpulse/v1/vessels/vessel-001/status", b"garbage") is None
