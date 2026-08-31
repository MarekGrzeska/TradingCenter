"""Reading further back than one provider request reaches. Every constraint here was measured
against the live demo API: 1000 candles per request, window <= (max - 1) x resolution, UTC, no zone."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from .dtos import Candle, CandleHistory, Resolution

# What the provider answers once a window falls past an instrument's oldest candle. The end of
# the data, not a failure: read as an error it throws away everything already collected.
HISTORY_EXHAUSTED = "error.prices.not-found"

MAX_BARS_PER_REQUEST = 1000

# One period in seconds. Unlike the streaming bucket map this includes DAY and WEEK: here the
# number only sizes a window, and overstating elapsed time costs a request, understating an error.
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
    """How wide a `from`/`to` window may be for ``bars`` candles. The minus one is the provider's
    rule, not an off-by-one guard: the window counts both edges. Measured — 999 pass, 1000 do not."""
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


def window_before(
    anchor: datetime, resolution: Resolution, bars: int, floor: datetime | None = None
) -> tuple[str, str]:
    """The `from`/`to` pair for the page immediately older than ``anchor``. ``floor`` raises the
    older edge, so a caller that named a lower bound spends no request on candles it will discard."""
    start = anchor - timedelta(seconds=window_seconds(resolution, bars))
    if floor is not None and floor > start:
        start = floor
    return iso_utc(start), iso_utc(anchor)


# Returns the page, or None once the instrument has no data older than the window —
# which the provider reports as an error and this module treats as an ending.
FetchPage = Callable[[str | None, str | None, int], Awaitable[list[Candle] | None]]

# Answers "is this instrument's market open right now". Injected rather than reached for,
# same as ``FetchPage``, so the rule below stays testable without a transport underneath.
MarketOpen = Callable[[], Awaitable[bool]]

# The resolutions whose period is a fixed number of seconds, so "is now inside this candle's
# period" is exact. DAY and WEEK follow the venue's session, and one computed from UTC is wrong.
FIXED_PERIOD = frozenset(
    {
        Resolution.MINUTE,
        Resolution.MINUTE_5,
        Resolution.MINUTE_15,
        Resolution.MINUTE_30,
        Resolution.HOUR,
        Resolution.HOUR_4,
    }
)


async def mark_forming(
    candles: list[Candle],
    resolution: Resolution,
    now: datetime,
    market_open: MarketOpen | None = None,
) -> list[Candle]:
    """Say which candle, if any, covers a period that has not finished — only the newest can.
    ``market_open`` is awaited for DAY and WEEK alone, so a deep read never spends the request."""
    if not candles:
        return candles

    newest = candles[-1]
    started = parse_candle_ts(newest.ts)
    if started + timedelta(seconds=PERIOD_SECONDS[resolution]) <= now:
        return candles

    if resolution in FIXED_PERIOD:
        running = True
    elif market_open is None:
        # Nothing to ask. Left closed rather than guessed: storing a moving candle as settled
        # is the silent failure, and withholding one forever is the loud one.
        running = False
    else:
        running = await market_open()

    if not running:
        return candles
    return [*candles[:-1], newest.model_copy(update={"forming": True})]


async def collect(
    symbol: str,
    resolution: Resolution,
    bars: int,
    fetch_page: FetchPage,
    still_wanted: Callable[[], Awaitable[bool]] | None = None,
    anchor: datetime | None = None,
    after: datetime | None = None,
) -> CandleHistory:
    """Page backwards until ``bars`` candles are held, or the instrument runs out. The cursor is
    the oldest candle collected, never the clock — a calendar-stepped one skips the days it assumed."""
    per_request = page_size(bars)
    collected: list[Candle] = []
    requests = 0
    cursor: datetime | None = None
    history_ended = False
    reached_floor = False

    while len(collected) < bars:
        if still_wanted is not None and not await still_wanted():
            break
        edge = cursor or anchor
        if edge is None:
            date_from, date_to = (None, None)
        else:
            if after is not None and after >= edge:
                # The floor is already at or past this window's newer edge: everything
                # left to ask for is older than the caller wants.
                reached_floor = True
                break
            date_from, date_to = window_before(edge, resolution, per_request, floor=after)
        # Whether this window's older edge *is* the floor rather than the calendar. It decides
        # what running out means, so it is computed once — the two ways must never disagree.
        on_the_floor = (
            after is not None
            and edge is not None
            and edge - timedelta(seconds=window_seconds(resolution, per_request)) <= after
        )
        requests += 1
        page = await fetch_page(date_from, date_to, per_request)

        if page:
            collected.extend(page)
            oldest = parse_candle_ts(page[0].ts)
            if after is not None and oldest <= after:
                reached_floor = True
                break
            if cursor is None or oldest < cursor:
                cursor = oldest
                continue

        # Nothing left to ask for. Away from the floor that is the provider's own bottom; at the
        # floor it says only that the caller's bound was reached. Measured twice, six weeks each.
        if on_the_floor:
            reached_floor = True
        elif collected:
            history_ended = True
        break

    # Pages overlap at their edges, and a consumer charting this needs time strictly
    # increasing and unique.
    collected.sort(key=lambda c: c.ts)
    unique = [c for i, c in enumerate(collected) if i == 0 or c.ts != collected[i - 1].ts]
    if after is not None:
        # A page is only ever clamped at its edges, so one can still carry candles from
        # before the floor. The floor is the caller's promise, not an approximation.
        unique = [c for c in unique if parse_candle_ts(c.ts) >= after]
    trimmed = unique[-bars:]

    return CandleHistory(
        candles=trimmed,
        count=len(trimmed),
        requested=bars,
        requests=requests,
        resolution=resolution,
        first_ts=trimmed[0].ts if trimmed else None,
        last_ts=trimmed[-1].ts if trimmed else None,
        # Never because the caller's own floor was reached: a consumer stores this as the
        # provider's permanent boundary and would stop ever reaching deeper.
        history_ended=history_ended and not reached_floor and len(trimmed) < bars,
    )
