"""Ingestion worker: stores telemetry in InfluxDB and turns readings into alerts."""

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import aiomqtt
from influxdb_client_3 import InfluxDBClient3, Point
from pydantic import ValidationError

from fleetpulse_backend.alerts.engine import AlertEngine
from fleetpulse_backend.alerts.store import AlertStore
from fleetpulse_backend.config import Settings
from fleetpulse_backend.db.session import create_engine, create_sessionmaker
from fleetpulse_backend.mqtt import RECONNECT_DELAY_S, event_loop_factory, payload_bytes
from fleetpulse_backend.worker.ingest import (
    BatchWriter,
    InvalidTelemetryError,
    parse_telemetry,
    to_point,
)
from fleetpulse_contracts import StatusMessage
from fleetpulse_contracts.alerts import AlertEvent
from fleetpulse_contracts.topics import (
    ALERTS_TOPIC,
    STATUS_SUBSCRIPTION,
    TELEMETRY_SUBSCRIPTION,
    vessel_id_from_topic,
)

logger = logging.getLogger("fleetpulse.worker")

RELOAD_RULES_S = 30
SWEEP_S = 5
MAX_QUEUED_EVENTS = 1000


async def guarded(task: Awaitable[None], what: str) -> None:
    """Alert problems (e.g. the database restarting) must never stop telemetry ingestion."""
    try:
        await task
    except Exception:
        logger.exception("%s failed", what)


async def handle_messages(client: aiomqtt.Client, writer: BatchWriter, engine: AlertEngine) -> None:
    async for message in client.messages:
        topic = str(message.topic)
        now = datetime.now(UTC)
        if topic.endswith("/status"):
            try:
                status = StatusMessage.model_validate_json(payload_bytes(message))
            except ValidationError:
                continue
            await guarded(engine.on_status(status, now), "status handling")
            continue
        try:
            telemetry = parse_telemetry(topic, payload_bytes(message))
        except InvalidTelemetryError as error:
            logger.warning("rejected message on %s: %s", topic, error)
            await guarded(
                engine.on_invalid(vessel_id_from_topic(topic), str(error), now), "alerting"
            )
            continue
        writer.add(to_point(telemetry))
        if writer.is_full_batch:
            await writer.flush()
        await guarded(engine.on_telemetry(telemetry, now), "alerting")


async def publish_events(client: aiomqtt.Client, outbox: asyncio.Queue[AlertEvent]) -> None:
    while True:
        event = await outbox.get()
        await client.publish(ALERTS_TOPIC, event.model_dump_json(), qos=1)


async def run_mqtt(
    settings: Settings,
    writer: BatchWriter,
    engine: AlertEngine,
    outbox: asyncio.Queue[AlertEvent],
) -> None:
    while True:
        try:
            async with aiomqtt.Client(
                settings.mqtt_host,
                settings.mqtt_port,
                identifier="fleetpulse-worker",
                username=settings.mqtt_username,
                password=settings.mqtt_password_value,
            ) as client:
                await client.subscribe(TELEMETRY_SUBSCRIPTION, qos=0)
                await client.subscribe(STATUS_SUBSCRIPTION, qos=1)
                logger.info("subscribed to telemetry and status")
                async with asyncio.TaskGroup() as group:
                    group.create_task(handle_messages(client, writer, engine))
                    group.create_task(publish_events(client, outbox))
        except* aiomqtt.MqttError as errors:
            logger.warning("MQTT error (%s), reconnecting", errors.exceptions[0])
            await asyncio.sleep(RECONNECT_DELAY_S)


async def every(seconds: float, task: str, action: Callable[[], Awaitable[None]]) -> None:
    while True:
        await asyncio.sleep(seconds)
        await guarded(action(), task)


async def main() -> None:
    settings = Settings()
    influx = InfluxDBClient3(
        host=settings.influx_url, database=settings.influx_database, token=settings.influx_token
    )
    database = create_engine(settings.database_url)
    store = AlertStore(create_sessionmaker(database))

    async def write(points: list[Point]) -> None:
        # The client is synchronous; run it in a thread so MQTT handling is not blocked.
        await asyncio.to_thread(influx.write, record=points)

    writer = BatchWriter(
        write,
        batch_size=settings.worker_batch_size,
        max_buffered=settings.worker_max_buffered_points,
    )

    # Events wait here while the broker is unreachable; the oldest are dropped if full.
    outbox: asyncio.Queue[AlertEvent] = asyncio.Queue(MAX_QUEUED_EVENTS)

    async def publish(event: AlertEvent) -> None:
        if outbox.full():
            outbox.get_nowait()
        outbox.put_nowait(event)

    engine = AlertEngine(store, publish)

    async def reload() -> None:
        engine.load(await store.load_rules(), await store.load_vessels(), await store.load_open())

    async def sweep() -> None:
        await engine.sweep(datetime.now(UTC))

    await guarded(reload(), "loading alert rules")
    try:
        async with asyncio.TaskGroup() as group:
            group.create_task(run_mqtt(settings, writer, engine, outbox))
            group.create_task(every(settings.worker_flush_interval_s, "flush", writer.flush))
            group.create_task(every(RELOAD_RULES_S, "reloading alert rules", reload))
            group.create_task(every(SWEEP_S, "offline sweep", sweep))
    finally:
        await writer.flush()
        influx.close()
        await database.dispose()


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main(), loop_factory=event_loop_factory())


if __name__ == "__main__":
    run()
