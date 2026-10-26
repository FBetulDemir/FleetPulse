"""End-to-end smoke test for a running stack (`docker compose up`).

Passes when:
- the web server serves the Angular app, including deep links,
- telemetry flows simulator -> MQTT -> API -> WebSocket, through the web server's proxy,
- telemetry flows simulator -> MQTT -> worker -> InfluxDB.
"""

import asyncio
import json
import sys
import time
import urllib.parse
import urllib.request
from typing import Any

from websockets.asyncio.client import connect
from websockets.exceptions import InvalidHandshake

WEB_URL = "http://localhost:8080"
WS_URL = "ws://localhost:8080/ws"
INFLUX_URL = "http://localhost:8181"
TIMEOUT_S = 90


def serves_app_on_deep_link() -> bool:
    # A route the server does not know must still return the app (client-side routing).
    with urllib.request.urlopen(f"{WEB_URL}/some/deep/link", timeout=5) as response:
        return "<app-root" in response.read().decode()


async def wait_for_web_app(deadline: float) -> None:
    while True:
        try:
            if await asyncio.to_thread(serves_app_on_deep_link):
                return
        except OSError:
            pass
        if time.monotonic() > deadline:
            raise TimeoutError("web app not served")
        await asyncio.sleep(2)


async def wait_for_live_telemetry(deadline: float) -> dict[str, Any]:
    while True:
        try:
            async with connect(WS_URL) as ws:
                await ws.send(json.dumps({"type": "subscribe", "channel": "fleet"}))
                async with asyncio.timeout(max(0.0, deadline - time.monotonic())):
                    while True:
                        event: dict[str, Any] = json.loads(await ws.recv())
                        if event["type"] == "telemetry":
                            return event
        except (OSError, InvalidHandshake):
            if time.monotonic() > deadline:
                raise
            await asyncio.sleep(2)


def stored_point_count() -> int:
    query = urllib.parse.urlencode(
        {"db": "fleetpulse", "q": "SELECT COUNT(*) AS n FROM vessel_telemetry", "format": "json"}
    )
    with urllib.request.urlopen(f"{INFLUX_URL}/api/v3/query_sql?{query}", timeout=5) as response:
        rows: list[dict[str, int]] = json.load(response)
    return rows[0]["n"] if rows else 0


async def wait_for_stored_telemetry(deadline: float) -> int:
    while True:
        try:
            count = await asyncio.to_thread(stored_point_count)
            if count > 0:
                return count
        except OSError:
            pass  # InfluxDB not ready, or the table does not exist yet
        if time.monotonic() > deadline:
            raise TimeoutError("no telemetry stored in InfluxDB")
        await asyncio.sleep(2)


async def main() -> None:
    deadline = time.monotonic() + TIMEOUT_S
    await wait_for_web_app(deadline)
    print("web app served")
    event = await wait_for_live_telemetry(deadline)
    print(f"live telemetry received over WebSocket from {event['vessel_id']}")
    count = await wait_for_stored_telemetry(deadline)
    print(f"{count} telemetry points stored in InfluxDB")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (TimeoutError, OSError, InvalidHandshake) as error:
        print(f"smoke test failed: {error!r}", file=sys.stderr)
        sys.exit(1)
