"""Simple rate-limiter that enforces a maximum number of requests per minute."""

from __future__ import annotations

import asyncio
import time


class RateLimiter:
    """Token-bucket style rate limiter.

    Parameters
    ----------
    requests_per_minute:
        Maximum allowed requests per minute.  Each call to :meth:`acquire`
        will block (``await``) until the next request is allowed.
    """

    def __init__(self, requests_per_minute: int = 100) -> None:
        self._delay = max(0.001, 60.0 / max(1, requests_per_minute))
        self._last: float = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until the next request is permitted."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            wait = self._delay - elapsed
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.monotonic()
