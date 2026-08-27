"""How long a bar lasts, and the window that holds a given number of them. The archive's vocabulary, copied rather
than imported, so a change there is a deliberate edit here; `DAY` and `WEEK` are approximations that err safely."""

from __future__ import annotations

from datetime import datetime, timedelta

PERIOD_SECONDS: dict[str, int] = {
    "MINUTE": 60,
    "MINUTE_5": 300,
    "MINUTE_15": 900,
    "MINUTE_30": 1_800,
    "HOUR": 3_600,
    "HOUR_4": 14_400,
    "DAY": 86_400,
    "WEEK": 604_800,
}

RESOLUTIONS = tuple(PERIOD_SECONDS)


class UnknownResolution(ValueError):
    def __init__(self, resolution: str) -> None:
        self.resolution = resolution
        super().__init__(
            f"{resolution!r} is not one of the archive's resolutions: "
            f"{', '.join(RESOLUTIONS)}"
        )


def period_length(resolution: str) -> timedelta:
    try:
        return timedelta(seconds=PERIOD_SECONDS[resolution])
    except KeyError:
        raise UnknownResolution(resolution) from None


def window_for(resolution: str, *, last_bar: datetime, bars: int) -> tuple[datetime, datetime]:
    """The `[from, to)` range holding `bars` bars ending with the one that opened at `last_bar`. The upper
    bound is exclusive and one period past that opening, or the bar being decided on falls out of its own read."""
    period = period_length(resolution)
    return last_bar - period * (bars - 1), last_bar + period


def bars_between(resolution: str, start: datetime, end: datetime) -> int:
    """How many bars a range holds, rounded up. Used to size a read against the archive's
    per-request ceiling, so overstating is the safe direction."""
    period = period_length(resolution).total_seconds()
    span = max((end - start).total_seconds(), 0.0)
    return int(span // period) + 1
