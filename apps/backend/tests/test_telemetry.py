import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from influxdb_client_3 import InfluxDBClient3

from fleetpulse_backend.db.models import Role, Vessel, VesselType
from fleetpulse_backend.telemetry import bucket_seconds
from fleetpulse_backend.worker.ingest import to_point
from fleetpulse_contracts import TelemetryMessage

from .conftest import DbClient, Sessionmaker, make_db_client

# A fixed point in the recent past, so tests do not depend on the current second.
NOW = datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(minutes=5)


def reading(minutes_ago: float, vessel_id: str = "vessel-001", **values: Any) -> TelemetryMessage:
    fields: dict[str, Any] = {
        "latitude": 57.70,
        "longitude": 11.95,
        "speed_knots": 8.0,
        "course_degrees": 90.0,
        "battery_percent": 80.0,
        "battery_voltage": 25.2,
        "motor_temperature_c": 45.0,
        "ambient_temperature_c": 12.0,
        "status": "underway",
    }
    return TelemetryMessage(
        vessel_id=vessel_id,
        device_id=vessel_id.replace("vessel", "device"),
        timestamp=NOW - timedelta(minutes=minutes_ago),
        **{**fields, **values},
    )


class Telemetry:
    """A logged-in client, a registered vessel, and a way to store readings for it."""

    def __init__(self, db: DbClient, influx: InfluxDBClient3, vessel_id: uuid.UUID) -> None:
        self.db = db
        self.client = db.client
        self.influx = influx
        self.url = f"/api/v1/vessels/{vessel_id}/telemetry"

    def store(self, *readings: TelemetryMessage) -> None:
        self.influx.write(record=[to_point(r) for r in readings])


@pytest.fixture
def telemetry(database_url: str, influx_url: str) -> Iterator[Telemetry]:
    # A fresh InfluxDB database per test keeps tests independent.
    database = f"test_{uuid.uuid4().hex}"
    influx = InfluxDBClient3(host=influx_url, database=database, token="unused")
    with make_db_client(database_url, influx_url=influx_url, influx_database=database) as db:
        vessel_id = uuid.uuid4()

        async def register(sessionmaker: Sessionmaker) -> None:
            async with sessionmaker() as session, session.begin():
                session.add(
                    Vessel(
                        id=vessel_id,
                        identifier="vessel-001",
                        name="Älvskutt",
                        vessel_type=VesselType.FERRY,
                        length_m=24.0,
                    )
                )

        db.run(register)
        db.login_as(Role.VIEWER)
        yield Telemetry(db, influx, vessel_id)
    influx.close()


def iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


# Latest


def test_latest_returns_the_most_recent_reading(telemetry: Telemetry) -> None:
    telemetry.store(reading(10, speed_knots=1.0), reading(2, speed_knots=7.5))

    response = telemetry.client.get(f"{telemetry.url}/latest")

    assert response.status_code == 200
    body = response.json()
    assert body["speed_knots"] == 7.5
    assert body["vessel_id"] == "vessel-001"
    assert body["timestamp"] == iso(NOW - timedelta(minutes=2))


def test_latest_ignores_other_vessels(telemetry: Telemetry) -> None:
    telemetry.store(reading(5, speed_knots=3.0), reading(1, "vessel-002", speed_knots=9.0))

    assert telemetry.client.get(f"{telemetry.url}/latest").json()["speed_knots"] == 3.0


def test_latest_is_404_without_data(telemetry: Telemetry) -> None:
    # A brand-new database has no table yet; that is "no data", not an error.
    response = telemetry.client.get(f"{telemetry.url}/latest")

    assert response.status_code == 404
    assert response.json()["detail"] == "No recent telemetry for this vessel"


def test_unknown_vessel_is_404(telemetry: Telemetry) -> None:
    response = telemetry.client.get(f"/api/v1/vessels/{uuid.uuid4()}/telemetry/latest")

    assert response.json()["detail"] == "Vessel not found"


def test_telemetry_requires_login(database_url: str) -> None:
    with make_db_client(database_url) as db:
        response = db.client.get(f"/api/v1/vessels/{uuid.uuid4()}/telemetry/latest")

        assert response.status_code == 401


# History


def test_history_buckets_with_min_max_and_average(telemetry: Telemetry) -> None:
    # Two readings in the first 10-second bucket of the range, one in a later bucket.
    start = NOW - timedelta(hours=1)
    telemetry.store(
        reading(60, speed_knots=4.0),
        reading(60 - 5 / 60, speed_knots=6.0),
        reading(30, speed_knots=10.0),
    )

    response = telemetry.client.get(
        f"{telemetry.url}/history",
        params={"metric": "speed_knots", "from": iso(start), "to": iso(NOW)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["bucket_seconds"] == 10
    assert [(b["avg"], b["min"], b["max"]) for b in body["buckets"]] == [
        (5.0, 4.0, 6.0),
        (10.0, 10.0, 10.0),
    ]
    assert body["buckets"][0]["time"] == iso(start)
    # Averaged over the raw readings, not over the buckets: (4 + 6 + 10) / 3.
    assert body["summary"] == {"avg": pytest.approx(20 / 3), "min": 4.0, "max": 10.0, "count": 3}


def test_history_only_includes_the_requested_range(telemetry: Telemetry) -> None:
    telemetry.store(reading(120, battery_percent=50.0), reading(30, battery_percent=70.0))

    response = telemetry.client.get(
        f"{telemetry.url}/history",
        params={
            "metric": "battery_percent",
            "from": iso(NOW - timedelta(hours=1)),
            "to": iso(NOW),
        },
    )

    assert [b["avg"] for b in response.json()["buckets"]] == [70.0]


def test_history_without_data_has_no_summary(telemetry: Telemetry) -> None:
    response = telemetry.client.get(f"{telemetry.url}/history", params={"metric": "speed_knots"})

    assert response.status_code == 200
    assert response.json()["buckets"] == []
    assert response.json()["summary"] is None


@pytest.mark.parametrize(
    "params",
    [
        {"metric": "course_degrees"},  # angles cannot be averaged
        {"metric": "speed_knots; DROP TABLE vessel_telemetry"},
        {"metric": "speed_knots", "from": iso(NOW), "to": iso(NOW - timedelta(hours=1))},
        {"metric": "speed_knots", "from": iso(NOW - timedelta(hours=73)), "to": iso(NOW)},
        {"metric": "speed_knots", "from": "2026-10-26T10:00:00"},  # no timezone
    ],
)
def test_history_rejects_invalid_queries(telemetry: Telemetry, params: dict[str, str]) -> None:
    response = telemetry.client.get(f"{telemetry.url}/history", params=params)

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"


@pytest.mark.parametrize(
    ("span", "expected"),
    [
        (timedelta(minutes=5), 1),
        (timedelta(hours=1), 10),
        (timedelta(hours=6), 60),
        (timedelta(hours=24), 300),
        (timedelta(hours=72), 900),
    ],
)
def test_bucket_size_keeps_charts_under_360_points(span: timedelta, expected: int) -> None:
    assert bucket_seconds(NOW - span, NOW) == expected
