"""What the API sends over MQTT: alert changes and commands to vessels.

Every API instance relays the alerts topic to its WebSocket clients, so publishing
there reaches all connected browsers, not only those on this instance.
"""

import logging
from typing import Protocol

from fleetpulse_backend.api.relay import MessagingUnavailableError, MqttLink
from fleetpulse_contracts.alerts import AlertEvent
from fleetpulse_contracts.commands import CommandMessage
from fleetpulse_contracts.topics import ALERTS_TOPIC, command_topic

logger = logging.getLogger("fleetpulse.api.events")


class Publisher(Protocol):
    async def publish_alert(self, event: AlertEvent) -> None:
        """Best effort: the change is already saved, so a failure is only logged."""
        ...

    async def send_command(self, vessel_id: str, command: CommandMessage) -> None:
        """Raises MessagingUnavailableError if the command could not be sent."""
        ...


class MqttPublisher:
    def __init__(self, link: MqttLink) -> None:
        self._link = link

    async def publish_alert(self, event: AlertEvent) -> None:
        try:
            await self._link.publish(ALERTS_TOPIC, event.model_dump_json())
        except MessagingUnavailableError:
            # Clients still see the change on their next refresh.
            logger.warning("could not publish %s event for alert %s", event.event, event.alert.id)

    async def send_command(self, vessel_id: str, command: CommandMessage) -> None:
        await self._link.publish(command_topic(vessel_id), command.model_dump_json())
