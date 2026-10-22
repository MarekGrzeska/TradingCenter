"""The time the loop and the providers agree on. In production it is the wall clock; in a simulation it runs faster, so a
film whose captions appear "two hours after upload" appears in minutes — and everything that schedules from it (the
retry after an hour, the day a budget turns over) runs on the same time, or the simulation would lie about its own
schedule."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class SimClock:
    """Wall time multiplied by `speed`, from the moment it was made. Monotonic underneath: a simulation must not go
    backwards because the machine's clock was corrected."""

    def __init__(self, speed: float = 1.0, *, start: datetime | None = None) -> None:
        if speed <= 0:
            raise ValueError(f"the simulation speed must be positive; got {speed}")
        self._speed = speed
        self._start = start or datetime.now(UTC)
        self._origin = time.monotonic()

    def now(self) -> datetime:
        return self._start + timedelta(seconds=(time.monotonic() - self._origin) * self._speed)


class ManualClock:
    """Moves only when told to. What a test uses, so that "two hours later" is one line."""

    def __init__(self, start: datetime | None = None) -> None:
        self._now = start or datetime(2026, 9, 27, 8, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self._now

    def advance(self, **delta: float) -> None:
        self._now += timedelta(**delta)
