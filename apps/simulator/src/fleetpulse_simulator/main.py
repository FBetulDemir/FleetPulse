"""Runs the simulated fleet. Each vessel has its own MQTT connection, like a real device."""

import asyncio
import contextlib
import logging
import random
import sys
from datetime import UTC, datetime

import aiomqtt

from fleetpulse_contracts import ConnectionState, StatusMessage
from fleetpulse_contracts.topics import status_topic, telemetry_topic
from fleetpulse_simulator.config import Settings
from fleetpulse_simulator.routes import ROUTES
from fleetpulse_simulator.vessel import Vessel

logger = logging.getLogger("fleetpulse.simulator")

RECONNECT_DELAY_S = 3.0


def build_fleet(settings: Settings) -> list[Vessel]:
    rng = random.Random(settings.random_seed)
    fleet = []
    for index in range(settings.vessel_count):
        number = f"{index + 1:03d}"
        fleet.append(
            Vessel(
                vessel_id=f"vessel-{number}",
                device_id=f"device-{number}",
                route=ROUTES[index],
                rng=random.Random(rng.random()),
                battery_percent=rng.uniform(55, 95),
                dock_remaining_s=rng.uniform(5, 90),  # stagger departures
            )
        )
    return fleet


async def run_vessel(vessel: Vessel, settings: Settings) -> None:
    offline = StatusMessage(
        vessel_id=vessel.vessel_id, device_id=vessel.device_id, state=ConnectionState.OFFLINE
    )
    will = aiomqtt.Will(
        status_topic(vessel.vessel_id), offline.model_dump_json(), qos=1, retain=True
    )
    loop = asyncio.get_running_loop()
    last_tick = loop.time()

    while True:
        try:
            async with aiomqtt.Client(
                settings.mqtt_host,
                settings.mqtt_port,
                identifier=vessel.device_id,
                will=will,
            ) as client:
                online = StatusMessage(
                    vessel_id=vessel.vessel_id,
                    device_id=vessel.device_id,
                    state=ConnectionState.ONLINE,
                    timestamp=datetime.now(UTC),
                )
                await client.publish(
                    status_topic(vessel.vessel_id), online.model_dump_json(), qos=1, retain=True
                )
                logger.info("%s connected", vessel.vessel_id)
                try:
                    while True:
                        now = loop.time()
                        vessel.step(now - last_tick)
                        last_tick = now
                        message = vessel.telemetry(datetime.now(UTC))
                        await client.publish(
                            telemetry_topic(vessel.vessel_id), message.model_dump_json(), qos=0
                        )
                        await asyncio.sleep(settings.publish_interval_s)
                except asyncio.CancelledError:
                    # A clean disconnect does not trigger the Last Will, so announce it ourselves.
                    final = offline.model_copy(update={"timestamp": datetime.now(UTC)})
                    await client.publish(
                        status_topic(vessel.vessel_id), final.model_dump_json(), qos=1, retain=True
                    )
                    raise
        except aiomqtt.MqttError as error:
            logger.warning("%s: MQTT error (%s), retrying", vessel.vessel_id, error)
            await asyncio.sleep(RECONNECT_DELAY_S)


async def main() -> None:
    settings = Settings()
    fleet = build_fleet(settings)
    logger.info("simulating %d vessels against %s", len(fleet), settings.mqtt_host)
    async with asyncio.TaskGroup() as group:
        for vessel in fleet:
            group.create_task(run_vessel(vessel, settings))


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    # aiomqtt needs a selector event loop; Windows defaults to the proactor loop.
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main(), loop_factory=loop_factory)


if __name__ == "__main__":
    run()
