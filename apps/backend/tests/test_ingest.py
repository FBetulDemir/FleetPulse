import json
from datetime import UTC, datetime
from typing import Any

import pytest
from influxdb_client_3 import Point

from fleetpulse_backend.worker.ingest import (
    BatchWriter,
    InvalidTelemetryError,
    parse_telemetry,
    to_point,
)

TOPIC = "fleetpulse/v1/vessels/vessel-001/telemetry"


def payload(**overrides: Any) -> bytes:
    data: dict[str, Any] = {
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
    data.update(overrides)
    return json.dumps(data).encode()


def test_parse_valid_message() -> None:
    assert parse_telemetry(TOPIC, payload()).vessel_id == "vessel-001"


@pytest.mark.parametrize("raw", [b"not json", b"{}", payload(latitude=200)])
def test_parse_rejects_invalid_payloads(raw: bytes) -> None:
    with pytest.raises(InvalidTelemetryError):
        parse_telemetry(TOPIC, raw)


def test_parse_rejects_vessel_publishing_on_another_vessels_topic() -> None:
    with pytest.raises(InvalidTelemetryError, match="does not match"):
        parse_telemetry("fleetpulse/v1/vessels/vessel-002/telemetry", payload())


def test_point_uses_ids_as_tags_and_readings_as_fields() -> None:
    line = to_point(parse_telemetry(TOPIC, payload())).to_line_protocol()

    timestamp_ns = int(datetime(2026, 10, 26, 10, 0, tzinfo=UTC).timestamp()) * 10**9

    assert line.startswith("vessel_telemetry,device_id=device-001,vessel_id=vessel-001 ")
    # Numbers must always be written as floats (no "i" suffix): InfluxDB rejects a field
    # whose type changes, e.g. battery_percent=76i followed by battery_percent=75.5.
    assert "battery_percent=76," in line
    assert 'status="underway"' in line
    assert line.endswith(f" {timestamp_ns}")


class FakeInflux:
    def __init__(self) -> None:
        self.batches: list[list[Point]] = []
        self.fail = False

    async def write(self, points: list[Point]) -> None:
        if self.fail:
            raise ConnectionError("influx down")
        self.batches.append(points)


def point(n: int) -> Point:
    return Point("m").field("n", n)


async def test_flush_writes_in_batches() -> None:
    influx = FakeInflux()
    writer = BatchWriter(influx.write, batch_size=2, max_buffered=100)
    for n in range(5):
        writer.add(point(n))

    await writer.flush()

    assert [len(batch) for batch in influx.batches] == [2, 2, 1]
    assert len(writer) == 0


async def test_failed_write_keeps_points_for_retry() -> None:
    influx = FakeInflux()
    writer = BatchWriter(influx.write, batch_size=10, max_buffered=100)
    points = [point(n) for n in range(3)]
    for p in points:
        writer.add(p)

    influx.fail = True
    await writer.flush()
    assert len(writer) == 3

    influx.fail = False
    await writer.flush()
    assert influx.batches == [points]


async def test_buffer_drops_oldest_points_when_full() -> None:
    influx = FakeInflux()
    writer = BatchWriter(influx.write, batch_size=10, max_buffered=3)
    points = [point(n) for n in range(5)]
    for p in points:
        writer.add(p)

    await writer.flush()

    assert writer.dropped == 2
    assert influx.batches == [points[2:]]
