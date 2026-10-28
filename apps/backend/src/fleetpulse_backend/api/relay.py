"""The API's connection to the MQTT broker.

Incoming: vessel telemetry, status and alert events are relayed into the live hub for
WebSocket clients. The API subscribes to the broker directly instead of going through
the worker, so live updates need no extra infrastructure. Invalid messages are skipped
here; recording them is the worker's job.

Outgoing: alert changes and vessel commands are published over the same connection.
"""

import asyncio
import logging

import aiomqtt
from pydantic import ValidationError

from fleetpulse_backend.api.hub import Event, LiveHub
from fleetpulse_backend.config import Settings
from fleetpulse_backend.mqtt import RECONNECT_DELAY_S, payload_bytes
from fleetpulse_contracts import StatusMessage, TelemetryMessage
from fleetpulse_contracts.alerts import AlertEvent
from fleetpulse_contracts.topics import (
    ALERTS_TOPIC,
    STATUS_SUBSCRIPTION,
    TELEMETRY_SUBSCRIPTION,
    vessel_id_from_topic,
)

logger = logging.getLogger("fleetpulse.api.relay")


def to_event(topic: str, payload: bytes) -> tuple[str, Event] | None:
    if topic == ALERTS_TOPIC:
        try:
            alert = AlertEvent.model_validate_json(payload)
        except ValidationError:
            return None
        return alert.alert.vessel_id, {
            "type": "alert",
            "vessel_id": alert.alert.vessel_id,
            "event": alert.event,
            "alert": alert.alert.model_dump(mode="json"),
        }
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


class MessagingUnavailableError(Exception):
    pass


class MqttLink:
    """One long-lived broker connection, kept open and reconnected by `run()`.

    Publishing reuses it instead of connecting per message: one client per process is
    the usual MQTT pattern, it keeps the broker's connection count steady, and a
    publish fails immediately (rather than after a connect timeout) when the broker is
    unreachable.
    """

    def __init__(self, settings: Settings, hub: LiveHub) -> None:
        self._settings = settings
        self._hub = hub
        self._client: aiomqtt.Client | None = None

    async def run(self) -> None:
        while True:
            try:
                async with aiomqtt.Client(
                    self._settings.mqtt_host,
                    self._settings.mqtt_port,
                    identifier="fleetpulse-api",
                    username=self._settings.mqtt_username,
                    password=self._settings.mqtt_password_value,
                ) as client:
                    await client.subscribe(TELEMETRY_SUBSCRIPTION, qos=0)
                    await client.subscribe(STATUS_SUBSCRIPTION, qos=1)
                    await client.subscribe(ALERTS_TOPIC, qos=1)
                    self._client = client
                    logger.info("connected to the broker, relaying live events")
                    async for message in client.messages:
                        result = to_event(str(message.topic), payload_bytes(message))
                        if result is not None:
                            self._hub.publish(*result)
            except aiomqtt.MqttError as error:
                logger.warning("MQTT error (%s), reconnecting", error)
            finally:
                self._client = None
            await asyncio.sleep(RECONNECT_DELAY_S)

    async def publish(self, topic: str, payload: str) -> None:
        client = self._client
        if client is None:
            raise MessagingUnavailableError("not connected to the broker")
        try:
            await client.publish(topic, payload, qos=1)
        except aiomqtt.MqttError as error:
            raise MessagingUnavailableError(str(error)) from error
