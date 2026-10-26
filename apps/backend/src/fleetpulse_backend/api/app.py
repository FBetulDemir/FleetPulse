import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator

import anyio
from fastapi import APIRouter, FastAPI, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from fleetpulse_backend.api.hub import LiveHub, Subscriber
from fleetpulse_backend.api.relay import relay_mqtt
from fleetpulse_backend.api.schemas import SubscriptionMessage
from fleetpulse_backend.config import Settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

health = APIRouter(prefix="/api/v1/health", tags=["health"])


@health.get("/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


async def receive_subscriptions(websocket: WebSocket, hub: LiveHub, subscriber: Subscriber) -> None:
    # Replies go through the subscriber's queue, so a "subscribed" confirmation always
    # arrives before the snapshot and live events of that channel.
    while True:
        raw = await websocket.receive_text()
        try:
            message = SubscriptionMessage.model_validate_json(raw)
        except ValidationError:
            subscriber.offer({"type": "error", "message": "invalid subscription message"})
            continue
        if message.type == "subscribe":
            subscriber.offer({"type": "subscribed", "channel": message.channel_key})
            hub.subscribe(subscriber, message.channel_key)
        else:
            hub.unsubscribe(subscriber, message.channel_key)
            subscriber.offer({"type": "unsubscribed", "channel": message.channel_key})


async def send_events(websocket: WebSocket, subscriber: Subscriber) -> None:
    while True:
        event = await subscriber.queue.get()
        await websocket.send_json(event)


def create_app(settings: Settings | None = None, *, relay: bool = True) -> FastAPI:
    settings = settings or Settings()

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.hub = LiveHub()
        relay_task = asyncio.create_task(relay_mqtt(settings, app.state.hub)) if relay else None
        yield
        if relay_task is not None:
            relay_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await relay_task

    app = FastAPI(
        title="FleetPulse API",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.include_router(health)

    @app.websocket("/ws")
    async def live_events(websocket: WebSocket) -> None:
        # Not authenticated yet; authentication is added together with login.
        await websocket.accept()
        hub: LiveHub = websocket.app.state.hub
        subscriber = hub.connect()
        try:
            # anyio (not asyncio.TaskGroup) because Starlette cancels connections with anyio.
            async with anyio.create_task_group() as group:
                group.start_soon(receive_subscriptions, websocket, hub, subscriber)
                group.start_soon(send_events, websocket, subscriber)
        except* WebSocketDisconnect:
            pass
        finally:
            hub.disconnect(subscriber)

    return app


app = create_app()
