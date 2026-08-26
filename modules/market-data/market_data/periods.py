"""One instant, two spellings. The gateway publishes a period start as an ISO string over REST and as
epoch seconds over the socket; both arrive here and leave as one instant, or the archive stores two."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

from .models import Resolution

# How long one period lasts. `DAY` and `WEEK` are here although their real boundary follows the venue:
# both uses — sizing a window, measuring staleness — err safely when a period is overstated.
PERIOD_SECONDS: dict[Resolution, int] = {
    Resolution.MINUTE: 60,
    Resolution.MINUTE_5: 300,
    Resolution.MINUTE_15: 900,
    Resolution.MINUTE_30: 1_800,
    Resolution.HOUR: 3_600,
    Resolution.HOUR_4: 14_400,
    Resolution.DAY: 86_400,
    Resolution.WEEK: 604_800,
}


def period_length(resolution: Resolution) -> timedelta:
    return timedelta(seconds=PERIOD_SECONDS[resolution])


def periods_between(resolution: Resolution, start: datetime, end: datetime) -> int:
    """How many candles of this resolution fit in `[start, end)`, rounded up. Calendar periods, so a
    market shut for part of the window yields fewer, never more — a safe overestimate."""
    if end <= start:
        return 0
    seconds = (end - start).total_seconds()
    return math.ceil(seconds / period_length(resolution).total_seconds())


def from_iso(ts: str) -> datetime:
    """A period start as the gateway's REST side spells it. A candle with no zone at all is read as
    UTC, the same assumption the gateway makes parsing its own output back."""
    if not ts or not ts.strip():
        raise ValueError("a candle arrived from the gateway with no timestamp at all")
    try:
        parsed = datetime.fromisoformat(ts)
    except ValueError as err:
        raise ValueError(f"a candle timestamp the gateway sent is unreadable: {ts!r}") from err
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def from_epoch_seconds(seconds: float) -> datetime:
    """A period start as the gateway's stream spells it."""
    return datetime.fromtimestamp(seconds, tz=UTC)


def from_epoch_millis(millis: float) -> datetime:
    """A quote's moment. Milliseconds, because that is what the provider sends and the
    gateway forwards unchanged — the one place the stream does not speak in seconds."""
    return datetime.fromtimestamp(millis / 1000, tz=UTC)
