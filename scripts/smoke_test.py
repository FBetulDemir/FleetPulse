"""End-to-end smoke test for a running stack (`docker compose up`).

Passes when telemetry flows simulator -> MQTT -> worker -> InfluxDB, and
simulator -> MQTT -> API -> WebSocket.
"""

import asyncio
import json
import sys
import time
import urllib.parse
import urllib.request
from typing import Any

from websockets.asyncio.client import connect

WS_URL = "ws://localhost:8000/ws"
INFLUX_URL = "http://localhost:8181"
TIMEOUT_S = 90


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
        except OSError:
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
            count = stored_point_count()
            if count > 0:
                return count
        except OSError:
            pass  # InfluxDB not ready, or the table does not exist yet
        if time.monotonic() > deadline:
            raise TimeoutError("no telemetry stored in InfluxDB")
        await asyncio.sleep(2)


async def main() -> None:
    deadline = time.monotonic() + TIMEOUT_S
    event = await wait_for_live_telemetry(deadline)
    print(f"live telemetry received over WebSocket from {event['vessel_id']}")
    count = await wait_for_stored_telemetry(deadline)
    print(f"{count} telemetry points stored in InfluxDB")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (TimeoutError, OSError) as error:
        print(f"smoke test failed: {error!r}", file=sys.stderr)
        sys.exit(1)
