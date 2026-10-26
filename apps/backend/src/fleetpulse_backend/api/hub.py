"""Fan-out of live events to WebSocket subscribers.

Each subscriber has a bounded queue. A slow client loses its oldest events instead of
slowing down everyone else or growing memory without limit.
"""

import asyncio
from typing import Any

FLEET_CHANNEL = "fleet"

Event = dict[str, Any]


def vessel_channel(vessel_id: str) -> str:
    return f"vessel:{vessel_id}"


class Subscriber:
    def __init__(self, max_queued: int) -> None:
        self.queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=max_queued)
        self.channels: set[str] = set()

    def offer(self, event: Event) -> None:
        if self.queue.full():
            self.queue.get_nowait()
        self.queue.put_nowait(event)


class LiveHub:
    def __init__(self, max_queued_per_subscriber: int = 100) -> None:
        self._max_queued = max_queued_per_subscriber
        self._subscribers: set[Subscriber] = set()
        # Latest events per vessel, sent to new subscribers so they do not start empty.
        self._latest_telemetry: dict[str, Event] = {}
        self._latest_status: dict[str, Event] = {}

    def connect(self) -> Subscriber:
        subscriber = Subscriber(self._max_queued)
        self._subscribers.add(subscriber)
        return subscriber

    def disconnect(self, subscriber: Subscriber) -> None:
        self._subscribers.discard(subscriber)

    def subscribe(self, subscriber: Subscriber, channel: str) -> None:
        subscriber.channels.add(channel)
        for event in self._snapshot(channel):
            subscriber.offer(event)

    def unsubscribe(self, subscriber: Subscriber, channel: str) -> None:
        subscriber.channels.discard(channel)

    def publish(self, vessel_id: str, event: Event) -> None:
        if event["type"] == "telemetry":
            self._latest_telemetry[vessel_id] = event
        elif event["type"] == "vessel_status":
            self._latest_status[vessel_id] = event

        channels = {FLEET_CHANNEL, vessel_channel(vessel_id)}
        for subscriber in self._subscribers:
            if subscriber.channels & channels:
                subscriber.offer(event)

    def _snapshot(self, channel: str) -> list[Event]:
        if channel == FLEET_CHANNEL:
            return [*self._latest_status.values(), *self._latest_telemetry.values()]
        vessel_id = channel.removeprefix("vessel:")
        return [
            event
            for event in (self._latest_status.get(vessel_id), self._latest_telemetry.get(vessel_id))
            if event is not None
        ]
