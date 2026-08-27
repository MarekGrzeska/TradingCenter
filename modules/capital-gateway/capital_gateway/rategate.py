"""The single gate every provider request passes through. capital.com allows 10 requests per second,
and a sliding window rather than a semaphore because the limit is a *rate*, not a concurrency."""

from __future__ import annotations

import asyncio
import time
from collections import deque


class RateGate:
    def __init__(self, limit: int = 10, per_seconds: float = 1.0) -> None:
        self._limit = limit
        self._per = per_seconds
        self._times: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        # The lock is held across the sleep on purpose: releasing it early would let
        # every waiter compute the same free slot and take it together.
        async with self._lock:
            while True:
                now = time.monotonic()
                while self._times and now - self._times[0] >= self._per:
                    self._times.popleft()
                if len(self._times) < self._limit:
                    self._times.append(now)
                    return
                await asyncio.sleep(self._per - (now - self._times[0]))
