"""One instant, two spellings.

`capital-gateway` publishes a candle's period start in two forms, and the split is
deliberate on its side: REST answers with an ISO string because that is what its OpenAPI
schema can describe, the WebSocket answers with epoch seconds because that is what a
charting library indexes by. Its README calls the seam deliberate rather than an
oversight, and for a chart it costs nothing.

For an archive it is a hazard. The same period reached by both roads has to land on the
same key, and a difference of a second — or a zone read off a string that never carried
one — writes a second candle instead of overwriting the first. Nothing else in this
module reads a gateway timestamp; both forms arrive here and leave as one instant.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

from .models import Resolution

# How long one period lasts. `DAY` and `WEEK` are here even though their real boundary
# follows the venue's session rather than the clock, because the two things this map is
# used for — sizing a window and measuring how stale a series is — both err safely when a
# period is overstated. Deriving a candle is not one of those things, and `rollups.py`
# takes only the resolutions it may floor.
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
    """How many candles of this resolution fit in `[start, end)`, rounded up.

    Calendar periods, not a session calendar — a market shut for part of the window
    yields fewer candles than this, never more, so the count this produces is a safe
    overestimate rather than a guess that could come in short.
    """
    if end <= start:
        return 0
    seconds = (end - start).total_seconds()
    return math.ceil(seconds / period_length(resolution).total_seconds())


def from_iso(ts: str) -> datetime:
    """A period start as the gateway's REST side spells it.

    The gateway stamps a `Z` onto the provider's `snapshotTimeUTC`, which the provider
    itself omits, so the usual form parses cleanly. A candle the provider gave only a
    broker-local `snapshotTime` for arrives with no zone at all, and that one is read as
    UTC — the same assumption the gateway makes when it parses its own output back, so
    the two modules are wrong together or right together, never quietly apart.
    """
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
