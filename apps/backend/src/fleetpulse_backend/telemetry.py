"""Reads stored telemetry from InfluxDB 3 with SQL."""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from influxdb_client_3 import InfluxDBClient3
from influxdb_client_3.exceptions.exceptions import InfluxDB3ClientQueryError

from fleetpulse_backend.worker.ingest import MEASUREMENT
from fleetpulse_contracts import TelemetryMessage

# InfluxDB 3 Core limits how much data one query may read (about 72 hours).
MAX_RANGE = timedelta(hours=72)
# Enough points for a smooth chart, few enough to stay fast.
MAX_BUCKETS = 360
BUCKET_STEPS_S = [1, 5, 10, 30, 60, 300, 600, 900, 1800, 3600]


class Metric(StrEnum):
    """Metrics with meaningful averages. Course is left out on purpose: it is an angle,
    and the average of 359° and 1° is 180°, which is wrong."""

    SPEED_KNOTS = "speed_knots"
    BATTERY_PERCENT = "battery_percent"
    BATTERY_VOLTAGE = "battery_voltage"
    MOTOR_TEMPERATURE_C = "motor_temperature_c"
    AMBIENT_TEMPERATURE_C = "ambient_temperature_c"


@dataclass(frozen=True)
class Bucket:
    time: datetime
    avg: float
    min: float
    max: float


@dataclass(frozen=True)
class Summary:
    avg: float
    min: float
    max: float
    count: int


class TelemetryUnavailableError(Exception):
    pass


def bucket_seconds(start: datetime, end: datetime) -> int:
    """The smallest standard bucket that keeps the chart within MAX_BUCKETS points."""
    span = (end - start).total_seconds()
    return next((step for step in BUCKET_STEPS_S if span / step <= MAX_BUCKETS), 3600)


class TelemetryStore:
    def __init__(self, client: InfluxDBClient3) -> None:
        self._client = client

    async def latest(self, vessel_id: str) -> TelemetryMessage | None:
        rows = await self._query(
            f"SELECT * FROM {MEASUREMENT} "
            # The time bound keeps the query within InfluxDB's per-query limit.
            "WHERE vessel_id = $vessel_id AND time > now() - INTERVAL '24 hours' "
            "ORDER BY time DESC LIMIT 1",
            vessel_id=vessel_id,
        )
        if not rows:
            return None
        row = dict(rows[0])
        row["timestamp"] = _utc(row.pop("time"))
        return TelemetryMessage.model_validate(row)

    async def history(
        self, vessel_id: str, metric: Metric, start: datetime, end: datetime
    ) -> tuple[int, list[Bucket], Summary | None]:
        step = bucket_seconds(start, end)
        params = {"vessel_id": vessel_id, "start": start.isoformat(), "end": end.isoformat()}
        where = "WHERE vessel_id = $vessel_id AND time >= $start AND time < $end"
        # The metric is a column name, which cannot be a query parameter. It is safe to
        # insert because it can only be one of the Metric enum's values.
        column = Metric(metric).value
        buckets_sql = (
            f"SELECT date_bin(INTERVAL '{step} seconds', time) AS bucket, "
            f"avg({column}) AS avg, min({column}) AS min, max({column}) AS max "
            f"FROM {MEASUREMENT} {where} GROUP BY bucket ORDER BY bucket"
        )
        # Computed from the raw readings: an average of bucket averages would be wrong
        # when buckets hold different numbers of readings.
        summary_sql = (
            f"SELECT avg({column}) AS avg, min({column}) AS min, max({column}) AS max, "
            f"count({column}) AS count FROM {MEASUREMENT} {where}"
        )
        bucket_rows, summary_rows = await asyncio.gather(
            self._query(buckets_sql, **params), self._query(summary_sql, **params)
        )
        buckets = [
            Bucket(time=_utc(row["bucket"]), avg=row["avg"], min=row["min"], max=row["max"])
            for row in bucket_rows
        ]
        summary_row = summary_rows[0] if summary_rows else None
        summary = Summary(**summary_row) if summary_row and summary_row.get("count") else None
        return step, buckets, summary

    def close(self) -> None:
        self._client.close()

    async def _query(self, sql: str, **params: str) -> list[dict[str, Any]]:
        try:
            table = await asyncio.to_thread(self._client.query, sql, query_parameters=params)
        except InfluxDB3ClientQueryError as error:
            # Before the first write the table does not exist yet: that just means no data.
            if "not found" in str(error):
                return []
            raise TelemetryUnavailableError(str(error)) from error
        except Exception as error:
            raise TelemetryUnavailableError(str(error)) from error
        rows: list[dict[str, Any]] = table.to_pylist()
        return rows


def _utc(value: datetime) -> datetime:
    # InfluxDB returns UTC timestamps without a timezone.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
