"""Runs the simulated fleet. Each vessel has its own MQTT connection, like a real device."""

import asyncio
import contextlib
import json
import logging
import random
import sys
from datetime import UTC, datetime

import aiomqtt
from pydantic import ValidationError

from fleetpulse_contracts import ConnectionState, StatusMessage, TelemetryMessage
from fleetpulse_contracts.commands import CommandMessage, Scenario
from fleetpulse_contracts.topics import command_topic, status_topic, telemetry_topic
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


def status_payload(vessel: Vessel, state: ConnectionState) -> str:
    return StatusMessage(
        vessel_id=vessel.vessel_id,
        device_id=vessel.device_id,
        state=state,
        timestamp=datetime.now(UTC),
    ).model_dump_json()


def invalid_payload(message: TelemetryMessage) -> str:
    """What a faulty sensor might send: an impossible battery level."""
    data = message.model_dump(mode="json")
    data["battery_percent"] = 250
    return json.dumps(data)


def parse_command(payload: bytes) -> Scenario | None:
    try:
        return CommandMessage.model_validate_json(payload).scenario
    except ValidationError:
        return None


class Ticker:
    """Time since the previous tick, kept across reconnects."""

    def __init__(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._last = self._loop.time()

    def elapsed(self) -> float:
        now = self._loop.time()
        elapsed, self._last = now - self._last, now
        return elapsed


async def publish_telemetry(
    client: aiomqtt.Client, vessel: Vessel, ticker: Ticker, interval_s: float
) -> None:
    announced_offline = False
    while True:
        vessel.step(ticker.elapsed())
        if vessel.silent:
            # Going offline on purpose: say so once, then send nothing.
            if not announced_offline:
                await client.publish(
                    status_topic(vessel.vessel_id),
                    status_payload(vessel, ConnectionState.OFFLINE),
                    qos=1,
                    retain=True,
                )
                announced_offline = True
        else:
            if announced_offline:
                await client.publish(
                    status_topic(vessel.vessel_id),
                    status_payload(vessel, ConnectionState.ONLINE),
                    qos=1,
                    retain=True,
                )
                announced_offline = False
            message = vessel.telemetry(datetime.now(UTC))
            payload = (
                invalid_payload(message) if vessel.sends_invalid_data else message.model_dump_json()
            )
            await client.publish(telemetry_topic(vessel.vessel_id), payload, qos=0)
        await asyncio.sleep(interval_s)


async def listen_for_commands(client: aiomqtt.Client, vessel: Vessel) -> None:
    async for message in client.messages:
        payload = message.payload if isinstance(message.payload, bytes) else b""
        scenario = parse_command(payload)
        if scenario is None:
            logger.warning("%s: ignored an invalid command", vessel.vessel_id)
            continue
        vessel.start_scenario(scenario)
        logger.info("%s: scenario %s", vessel.vessel_id, scenario.value)


async def run_vessel(vessel: Vessel, settings: Settings) -> None:
    offline = StatusMessage(
        vessel_id=vessel.vessel_id, device_id=vessel.device_id, state=ConnectionState.OFFLINE
    )
    will = aiomqtt.Will(
        status_topic(vessel.vessel_id), offline.model_dump_json(), qos=1, retain=True
    )
    ticker = Ticker()

    while True:
        try:
            async with aiomqtt.Client(
                settings.mqtt_host,
                settings.mqtt_port,
                identifier=vessel.device_id,
                will=will,
            ) as client:
                await client.subscribe(command_topic(vessel.vessel_id), qos=1)
                await client.publish(
                    status_topic(vessel.vessel_id),
                    status_payload(vessel, ConnectionState.ONLINE),
                    qos=1,
                    retain=True,
                )
                logger.info("%s connected", vessel.vessel_id)
                try:
                    async with asyncio.TaskGroup() as group:
                        group.create_task(
                            publish_telemetry(client, vessel, ticker, settings.publish_interval_s)
                        )
                        group.create_task(listen_for_commands(client, vessel))
                except asyncio.CancelledError:
                    # A clean disconnect does not trigger the Last Will, so announce it ourselves.
                    await client.publish(
                        status_topic(vessel.vessel_id),
                        status_payload(vessel, ConnectionState.OFFLINE),
                        qos=1,
                        retain=True,
                    )
                    raise
        except* aiomqtt.MqttError as errors:
            logger.warning("%s: MQTT error (%s), retrying", vessel.vessel_id, errors.exceptions[0])
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
