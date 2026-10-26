"""Turns raw MQTT telemetry into validated InfluxDB points and writes them in batches."""

import asyncio
import logging
from collections.abc import Awaitable, Callable

from influxdb_client_3 import Point
from pydantic import ValidationError

from fleetpulse_contracts import TelemetryMessage
from fleetpulse_contracts.topics import vessel_id_from_topic

logger = logging.getLogger("fleetpulse.worker")

MEASUREMENT = "vessel_telemetry"

WritePoints = Callable[[list[Point]], Awaitable[None]]


class InvalidTelemetryError(Exception):
    pass


def parse_telemetry(topic: str, payload: bytes) -> TelemetryMessage:
    try:
        message = TelemetryMessage.model_validate_json(payload)
    except ValidationError as error:
        raise InvalidTelemetryError(
            f"schema validation failed: {error.error_count()} errors"
        ) from error

    # A device may only publish about its own vessel.
    topic_vessel = vessel_id_from_topic(topic)
    if topic_vessel != message.vessel_id:
        raise InvalidTelemetryError(
            f"topic vessel {topic_vessel!r} does not match payload vessel {message.vessel_id!r}"
        )
    return message


def to_point(message: TelemetryMessage) -> Point:
    return (
        Point(MEASUREMENT)
        .tag("vessel_id", message.vessel_id)
        .tag("device_id", message.device_id)
        .field("latitude", message.latitude)
        .field("longitude", message.longitude)
        .field("speed_knots", message.speed_knots)
        .field("course_degrees", message.course_degrees)
        .field("battery_percent", message.battery_percent)
        .field("battery_voltage", message.battery_voltage)
        .field("motor_temperature_c", message.motor_temperature_c)
        .field("ambient_temperature_c", message.ambient_temperature_c)
        .field("status", message.status.value)
        .time(message.timestamp)
    )


class BatchWriter:
    """Buffers points and writes them in batches.

    If a write fails the points stay buffered and are retried on the next flush. The
    buffer is bounded: during a long outage the oldest points are dropped first, so
    memory use stays flat and the newest data survives.
    """

    def __init__(self, write: WritePoints, batch_size: int, max_buffered: int) -> None:
        self._write = write
        self._batch_size = batch_size
        self._max_buffered = max_buffered
        self._points: list[Point] = []
        self._flush_lock = asyncio.Lock()
        self.dropped = 0

    def __len__(self) -> int:
        return len(self._points)

    @property
    def is_full_batch(self) -> bool:
        return len(self._points) >= self._batch_size

    def add(self, point: Point) -> None:
        self._points.append(point)
        self._trim()

    async def flush(self) -> None:
        # The lock stops the periodic flush and a full-batch flush running at the same time.
        async with self._flush_lock:
            while self._points:
                batch = self._points[: self._batch_size]
                del self._points[: len(batch)]
                try:
                    await self._write(batch)
                except Exception:
                    logger.exception("writing %d points failed; will retry", len(batch))
                    self._points[:0] = batch
                    self._trim()
                    return

    def _trim(self) -> None:
        overflow = len(self._points) - self._max_buffered
        if overflow > 0:
            del self._points[:overflow]
            self.dropped += overflow
