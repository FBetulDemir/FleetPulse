import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from urllib.parse import urlsplit

import anyio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fleetpulse_backend.api import auth, health, vessels
from fleetpulse_backend.api.deps import ACCESS_COOKIE, authenticate
from fleetpulse_backend.api.hub import LiveHub, Subscriber
from fleetpulse_backend.api.problems import install_problem_handlers
from fleetpulse_backend.api.relay import relay_mqtt
from fleetpulse_backend.api.schemas import SubscriptionMessage
from fleetpulse_backend.config import Settings
from fleetpulse_backend.db.session import create_engine, create_sessionmaker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@dataclass(frozen=True)
class Rejection:
    code: int
    reason: str


# Application close codes (4000-4999), mirroring HTTP 401 and 403.
NOT_AUTHENTICATED = Rejection(4401, "Not authenticated")
FOREIGN_ORIGIN = Rejection(4403, "Origin not allowed")


async def check_websocket(websocket: WebSocket) -> Rejection | None:
    # Browsers attach cookies to WebSocket handshakes from any site, and CORS does not
    # apply to WebSockets. Checking the Origin blocks cross-site WebSocket hijacking.
    origin = websocket.headers.get("origin")
    if origin is not None and urlsplit(origin).netloc != websocket.headers.get("host"):
        return FOREIGN_ORIGIN

    sessionmaker: async_sessionmaker[AsyncSession] = websocket.app.state.sessionmaker
    async with sessionmaker() as session:
        user = await authenticate(
            websocket.cookies.get(ACCESS_COOKIE), session, websocket.app.state.settings
        )
    # Authenticated once at connect time. An open connection outlives the access token,
    # which is acceptable for read-only live data; the next reconnect checks again.
    return None if user is not None else NOT_AUTHENTICATED


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
        engine = create_engine(settings.database_url)
        app.state.sessionmaker = create_sessionmaker(engine)
        app.state.hub = LiveHub()
        relay_task = asyncio.create_task(relay_mqtt(settings, app.state.hub)) if relay else None
        yield
        if relay_task is not None:
            relay_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await relay_task
        await engine.dispose()

    app = FastAPI(
        title="FleetPulse API",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = settings
    install_problem_handlers(app)
    app.include_router(auth.router)
    app.include_router(health.router)
    app.include_router(vessels.router)

    @app.websocket("/ws")
    async def live_events(websocket: WebSocket) -> None:
        rejection = await check_websocket(websocket)
        await websocket.accept()
        if rejection is not None:
            # Accept first, then close with a code the browser can read. Rejecting the
            # handshake would only show the client a generic connection error.
            await websocket.close(code=rejection.code, reason=rejection.reason)
            return
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
