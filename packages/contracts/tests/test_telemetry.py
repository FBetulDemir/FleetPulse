import json
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from fleetpulse_contracts import NavigationStatus, TelemetryMessage
from fleetpulse_contracts.topics import telemetry_topic, vessel_id_from_topic


def valid_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": 1,
        "vessel_id": "vessel-001",
        "device_id": "device-001",
        "timestamp": "2026-10-26T10:00:00Z",
        "latitude": 57.7089,
        "longitude": 11.9746,
        "speed_knots": 5.2,
        "course_degrees": 142.5,
        "battery_percent": 76,
        "battery_voltage": 24.8,
        "motor_temperature_c": 42.3,
        "ambient_temperature_c": 12.5,
        "status": "underway",
    }
    payload.update(overrides)
    return payload


def test_parses_valid_json() -> None:
    message = TelemetryMessage.model_validate_json(json.dumps(valid_payload()))

    assert message.vessel_id == "vessel-001"
    assert message.status is NavigationStatus.UNDERWAY
    assert message.timestamp == datetime(2026, 10, 26, 10, 0, tzinfo=UTC)


def test_converts_timestamps_to_utc() -> None:
    message = TelemetryMessage.model_validate(valid_payload(timestamp="2026-10-26T12:00:00+02:00"))

    assert message.timestamp == datetime(2026, 10, 26, 10, 0, tzinfo=UTC)
    assert message.timestamp.utcoffset() is not None


@pytest.mark.parametrize(
    "overrides",
    [
        {"timestamp": "2026-10-26T10:00:00"},  # no timezone
        {"latitude": 91},
        {"course_degrees": 360},
        {"battery_percent": -1},
        {"speed_knots": 400},
        {"status": "flying"},
        {"schema_version": 2},
        {"vessel_id": "Vessel 1"},
        {"unexpected": "field"},
    ],
)
def test_rejects_invalid_payloads(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        TelemetryMessage.model_validate(valid_payload(**overrides))


def test_rejects_missing_fields() -> None:
    payload = valid_payload()
    del payload["battery_percent"]

    with pytest.raises(ValidationError):
        TelemetryMessage.model_validate(payload)


def test_topic_round_trip() -> None:
    assert vessel_id_from_topic(telemetry_topic("vessel-007")) == "vessel-007"


@pytest.mark.parametrize(
    "topic",
    ["fleetpulse/v1/vessels//telemetry", "fleetpulse/v2/vessels/a/telemetry", "other/topic"],
)
def test_vessel_id_from_unexpected_topic_is_none(topic: str) -> None:
    assert vessel_id_from_topic(topic) is None
