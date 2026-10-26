import time
from collections import deque
from collections.abc import Callable


class RateLimiter:
    """Allows at most `limit` actions per key in any `window_s` seconds (sliding window).

    Kept in memory, so each API instance counts separately. That is enough to stop a
    demo button from being hammered; a shared limit would need Redis or the database.
    """

    def __init__(
        self, limit: int, window_s: float, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._limit = limit
        self._window_s = window_s
        self._clock = clock
        self._events: dict[str, deque[float]] = {}

    def allow(self, key: str) -> bool:
        now = self._clock()
        events = self._events.setdefault(key, deque())
        while events and events[0] <= now - self._window_s:
            events.popleft()
        if len(events) >= self._limit:
            return False
        events.append(now)
        return True
