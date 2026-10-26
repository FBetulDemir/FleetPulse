import asyncio
import sys
from collections.abc import Callable

import aiomqtt

RECONNECT_DELAY_S = 3.0


def event_loop_factory() -> Callable[[], asyncio.AbstractEventLoop] | None:
    """aiomqtt needs a selector event loop; Windows defaults to the proactor loop."""
    return asyncio.SelectorEventLoop if sys.platform == "win32" else None


def payload_bytes(message: aiomqtt.Message) -> bytes:
    payload = message.payload
    if isinstance(payload, bytes | bytearray):
        return bytes(payload)
    if isinstance(payload, str):
        return payload.encode()
    return b""
