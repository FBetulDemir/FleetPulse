"""Publishes alert changes made through the API (acknowledgements) to MQTT.

Every API instance relays the alerts topic to its WebSocket clients, so publishing
there reaches all connected browsers, not only those on this instance.
"""

import logging
from typing import Protocol

import aiomqtt

from fleetpulse_backend.config import Settings
from fleetpulse_contracts.alerts import AlertEvent
from fleetpulse_contracts.topics import ALERTS_TOPIC

logger = logging.getLogger("fleetpulse.api.events")


class AlertEventPublisher(Protocol):
    async def publish(self, event: AlertEvent) -> None: ...


class MqttAlertEventPublisher:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def publish(self, event: AlertEvent) -> None:
        # Acknowledgements are rare, so a short-lived connection is simpler than sharing one.
        try:
            async with aiomqtt.Client(self._settings.mqtt_host, self._settings.mqtt_port) as client:
                await client.publish(ALERTS_TOPIC, event.model_dump_json(), qos=1)
        except aiomqtt.MqttError:
            # The change is already saved; clients see it on their next refresh.
            logger.warning("could not publish %s event for alert %s", event.event, event.alert.id)
