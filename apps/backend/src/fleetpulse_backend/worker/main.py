"""Ingestion worker: subscribes to vessel telemetry and stores it in InfluxDB."""

import asyncio
import contextlib
import logging

import aiomqtt
from influxdb_client_3 import InfluxDBClient3, Point

from fleetpulse_backend.config import Settings
from fleetpulse_backend.mqtt import RECONNECT_DELAY_S, event_loop_factory, payload_bytes
from fleetpulse_backend.worker.ingest import (
    BatchWriter,
    InvalidTelemetryError,
    parse_telemetry,
    to_point,
)
from fleetpulse_contracts.topics import TELEMETRY_SUBSCRIPTION

logger = logging.getLogger("fleetpulse.worker")


async def consume(settings: Settings, writer: BatchWriter) -> None:
    while True:
        try:
            async with aiomqtt.Client(
                settings.mqtt_host, settings.mqtt_port, identifier="fleetpulse-worker"
            ) as client:
                await client.subscribe(TELEMETRY_SUBSCRIPTION, qos=0)
                logger.info("subscribed to %s", TELEMETRY_SUBSCRIPTION)
                async for message in client.messages:
                    try:
                        telemetry = parse_telemetry(str(message.topic), payload_bytes(message))
                    except InvalidTelemetryError as error:
                        logger.warning("rejected message on %s: %s", message.topic, error)
                        continue
                    writer.add(to_point(telemetry))
                    if writer.is_full_batch:
                        await writer.flush()
        except aiomqtt.MqttError as error:
            logger.warning("MQTT error (%s), reconnecting", error)
            await asyncio.sleep(RECONNECT_DELAY_S)


async def flush_periodically(writer: BatchWriter, interval_s: float) -> None:
    while True:
        await asyncio.sleep(interval_s)
        await writer.flush()


async def main() -> None:
    settings = Settings()
    influx = InfluxDBClient3(
        host=settings.influx_url, database=settings.influx_database, token=settings.influx_token
    )

    async def write(points: list[Point]) -> None:
        # The client is synchronous; run it in a thread so MQTT handling is not blocked.
        await asyncio.to_thread(influx.write, record=points)

    writer = BatchWriter(
        write,
        batch_size=settings.worker_batch_size,
        max_buffered=settings.worker_max_buffered_points,
    )
    try:
        async with asyncio.TaskGroup() as group:
            group.create_task(consume(settings, writer))
            group.create_task(flush_periodically(writer, settings.worker_flush_interval_s))
    finally:
        await writer.flush()
        influx.close()


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main(), loop_factory=event_loop_factory())


if __name__ == "__main__":
    run()
