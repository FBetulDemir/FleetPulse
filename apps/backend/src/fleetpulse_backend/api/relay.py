"""Relays vessel telemetry and status from MQTT into the live hub.

The API subscribes to the broker directly instead of going through the worker, so live
updates need no extra infrastructure (see ADR-005). Invalid messages are skipped here;
recording them is the worker's job.
"""

import asyncio
import logging

import aiomqtt
from pydantic import ValidationError

from fleetpulse_backend.api.hub import Event, LiveHub
from fleetpulse_backend.config import Settings
from fleetpulse_backend.mqtt import RECONNECT_DELAY_S, payload_bytes
from fleetpulse_contracts import StatusMessage, TelemetryMessage
from fleetpulse_contracts.topics import (
    STATUS_SUBSCRIPTION,
    TELEMETRY_SUBSCRIPTION,
    vessel_id_from_topic,
)

logger = logging.getLogger("fleetpulse.api.relay")


def to_event(topic: str, payload: bytes) -> tuple[str, Event] | None:
    vessel_id = vessel_id_from_topic(topic)
    if vessel_id is None:
        return None
    try:
        if topic.endswith("/telemetry"):
            telemetry = TelemetryMessage.model_validate_json(payload)
            if telemetry.vessel_id != vessel_id:
                return None
            return vessel_id, {
                "type": "telemetry",
                "vessel_id": vessel_id,
                "data": telemetry.model_dump(mode="json"),
            }
        if topic.endswith("/status"):
            status = StatusMessage.model_validate_json(payload)
            if status.vessel_id != vessel_id:
                return None
            return vessel_id, {
                "type": "vessel_status",
                "vessel_id": vessel_id,
                "state": status.state.value,
            }
    except ValidationError:
        return None
    return None


async def relay_mqtt(settings: Settings, hub: LiveHub) -> None:
    while True:
        try:
            async with aiomqtt.Client(
                settings.mqtt_host, settings.mqtt_port, identifier="fleetpulse-api"
            ) as client:
                await client.subscribe(TELEMETRY_SUBSCRIPTION, qos=0)
                await client.subscribe(STATUS_SUBSCRIPTION, qos=1)
                logger.info("relaying live vessel events")
                async for message in client.messages:
                    result = to_event(str(message.topic), payload_bytes(message))
                    if result is not None:
                        hub.publish(*result)
        except aiomqtt.MqttError as error:
            logger.warning("MQTT error (%s), reconnecting", error)
            await asyncio.sleep(RECONNECT_DELAY_S)
