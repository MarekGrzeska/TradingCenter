"""Reading further back than one provider request reaches.

Every constraint encoded here was measured against the live demo API, not read from
documentation:

    max per request        1000            (1001 -> error.invalid.max)
    window width           <= (max - 1) x resolution
    from/to format         YYYY-MM-DDTHH:MM:SS, UTC, no zone
    result direction       forward from `from`, not backwards from `to`
    past the oldest candle error.prices.not-found
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from .dtos import Candle, CandleHistory, Resolution

# What the provider answers once a window falls past an instrument's oldest candle. It
# is the end of the data, not a failure, and the difference matters: treating it as an
# error throws away everything already collected.
HISTORY_EXHAUSTED = "error.prices.not-found"

MAX_BARS_PER_REQUEST = 1000

# One period in seconds. Unlike the streaming bucket map this one includes DAY and WEEK:
# here the number only sizes a request window, and a calendar-derived width always
# *overstates* elapsed time (weekends, holidays), so it understates how many candles fit.
# Erring that way costs an extra request; erring the other way costs an error.
PERIOD_SECONDS: dict[Resolution, int] = {
    Resolution.MINUTE: 60,
    Resolution.MINUTE_5: 300,
    Resolution.MINUTE_15: 900,
    Resolution.MINUTE_30: 1800,
    Resolution.HOUR: 3600,
    Resolution.HOUR_4: 14400,
    Resolution.DAY: 86400,
    Resolution.WEEK: 604800,
}


def window_seconds(resolution: Resolution, bars: int) -> int:
    """How wide a `from`/`to` window may be for ``bars`` candles.

    The minus one is not an off-by-one guard, it is the provider's rule: the window
    counts both edges, so 1000 periods asks for 1001 candles and is refused with
    ``error.invalid.max.daterange``. Measured — 999 steps pass, 1000 do not.
    """
    return (bars - 1) * PERIOD_SECONDS[resolution]


def iso_utc(moment: datetime) -> str:
    """The provider's format: UTC, second precision, and no zone marker at all. Sending
    an offset or a trailing Z is rejected."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S")


def parse_candle_ts(ts: str) -> datetime:
    """Read back what mapping wrote. The stored form carries the Z that the provider
    omits, so it round-trips through the standard parser."""
    parsed = datetime.fromisoformat(ts)
    # A candle mapped from `snapshotTime` rather than `snapshotTimeUTC` arrives naive.
    # Treating it as UTC is the same assumption the rest of the module makes.
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def page_size(bars: int) -> int:
    return min(MAX_BARS_PER_REQUEST, bars)


def window_before(anchor: datetime, resolution: Resolution, bars: int) -> tuple[str, str]:
    """The `from`/`to` pair for the page immediately older than ``anchor``."""
    return iso_utc(anchor - timedelta(seconds=window_seconds(resolution, bars))), iso_utc(anchor)


# Returns the page, or None once the instrument has no data older than the window —
# which the provider reports as an error and this module treats as an ending.
FetchPage = Callable[[str | None, str | None, int], Awaitable[list[Candle] | None]]


async def collect(
    symbol: str,
    resolution: Resolution,
    bars: int,
    fetch_page: FetchPage,
    still_wanted: Callable[[], Awaitable[bool]] | None = None,
) -> CandleHistory:
    """Page backwards until ``bars`` candles are held, or the instrument runs out.

    ``fetch_page(date_from, date_to, limit)`` is injected rather than taken from a
    client, so the paging rules can be tested without a transport underneath them.

    The cursor is the oldest candle actually collected, never the clock. A window
    derived from the calendar drifts: ask for 1000 five-minute candles ending Monday and
    the weekend hands back a couple of hundred, so a clock-stepped cursor would skip the
    days it assumed were there. Anchoring on data costs one more request instead.

    ``still_wanted`` is checked before each request. A deep read is up to thirty calls
    over half a minute; without it, a client that gave up ten seconds in keeps spending
    the rate budget on an answer nobody will read.
    """
    per_request = page_size(bars)
    collected: list[Candle] = []
    requests = 0
    cursor: datetime | None = None
    history_ended = False

    while len(collected) < bars:
        if still_wanted is not None and not await still_wanted():
            break
        date_from, date_to = (
            window_before(cursor, resolution, per_request) if cursor else (None, None)
        )
        requests += 1
        page = await fetch_page(date_from, date_to, per_request)

        # None is the provider's error.prices.not-found; an empty page is a window that
        # simply held no candles. Both mean there is nothing further back to ask for.
        if not page:
            history_ended = True
            break

        oldest = parse_candle_ts(page[0].ts)
        collected.extend(page)
        # No progress: the window returned nothing older than what we already hold, so
        # another identical request would return the same thing forever.
        if cursor is not None and oldest >= cursor:
            history_ended = True
            break
        cursor = oldest

    # Pages overlap at their edges, and a consumer charting this needs time strictly
    # increasing and unique.
    collected.sort(key=lambda c: c.ts)
    unique = [c for i, c in enumerate(collected) if i == 0 or c.ts != collected[i - 1].ts]
    trimmed = unique[-bars:]

    return CandleHistory(
        candles=trimmed,
        count=len(trimmed),
        requested=bars,
        requests=requests,
        resolution=resolution,
        first_ts=trimmed[0].ts if trimmed else None,
        last_ts=trimmed[-1].ts if trimmed else None,
        history_ended=history_ended and len(trimmed) < bars,
    )
