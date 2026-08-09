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


def window_before(
    anchor: datetime, resolution: Resolution, bars: int, floor: datetime | None = None
) -> tuple[str, str]:
    """The `from`/`to` pair for the page immediately older than ``anchor``.

    ``floor`` raises the older edge when the calendar-derived one would reach past it,
    so a caller that named a lower bound never spends a request on candles it is going
    to discard. It only ever narrows the window; a floor already older than the window
    changes nothing.
    """
    start = anchor - timedelta(seconds=window_seconds(resolution, bars))
    if floor is not None and floor > start:
        start = floor
    return iso_utc(start), iso_utc(anchor)


# Returns the page, or None once the instrument has no data older than the window —
# which the provider reports as an error and this module treats as an ending.
FetchPage = Callable[[str | None, str | None, int], Awaitable[list[Candle] | None]]


async def collect(
    symbol: str,
    resolution: Resolution,
    bars: int,
    fetch_page: FetchPage,
    still_wanted: Callable[[], Awaitable[bool]] | None = None,
    anchor: datetime | None = None,
    after: datetime | None = None,
) -> CandleHistory:
    """Page backwards until ``bars`` candles are held, or the instrument runs out.

    ``fetch_page(date_from, date_to, limit)`` is injected rather than taken from a
    client, so the paging rules can be tested without a transport underneath them.

    The cursor is the oldest candle actually collected, never the clock. A window
    derived from the calendar drifts: ask for 1000 five-minute candles ending Monday and
    the weekend hands back a couple of hundred, so a clock-stepped cursor would skip the
    days it assumed were there. Anchoring on data costs one more request instead.

    ``anchor`` only shapes the *first* page — every page after it is cursored on data,
    same as an unanchored read. Without it the first page asks for ``(None, None)``,
    which the provider reads as "the newest candles", so a caller wanting a window that
    ended months ago has no way to say so. ``None`` keeps today's behaviour: reach back
    from now.

    ``still_wanted`` is checked before each request. A deep read is up to thirty calls
    over half a minute; without it, a client that gave up ten seconds in keeps spending
    the rate budget on an answer nobody will read.

    ``after`` is a floor on how far back to reach, and it is a different thing from
    ``bars``. ``bars`` counts *candles*; an instrument that is shut half the week hands
    back ``bars`` candles spanning far more calendar time than ``bars`` periods, so a
    caller wanting "nothing older than this moment" cannot express it as a count. Paging
    stops once a page reaches the floor, windows are clamped to it so no request is spent
    on candles that would be discarded, and anything older that arrives inside a page is
    dropped before the answer is built. Reaching the floor is **not** ``history_ended``:
    that flag means the *provider* has nothing older, and a consumer records it as a
    permanent boundary — saying it because the caller asked for less would stop the next,
    deeper read from ever being made.
    """
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
        # Whether this window's older edge *is* the floor rather than the calendar. It
        # is the single thing that decides what running out of answers means, so it is
        # computed once here and consulted once below — the two ways of running out must
        # never be allowed to disagree about it.
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

        # Nothing left to ask for, reached by either of two routes that mean the same
        # thing. The window came back with no candles at all — `None` is the provider's
        # error.prices.not-found, `[]` a window it considers empty — or it came back
        # holding nothing older than what is already collected, so asking again would
        # return that same page forever.
        #
        # What running out *means* is not the same in both places it can happen, and the
        # difference is the whole reason `on_the_floor` exists. Away from the floor the
        # window spans a full `per_request` periods of calendar, so nothing older in it
        # is the provider's own bottom. At the floor the window is only `[floor, cursor]`
        # — often minutes wide — and running out of it says the caller's bound was
        # reached and nothing whatsoever about what the provider still holds below it.
        #
        # Measured twice, both times costing six weeks of candles. First as a not-found:
        # a 5-minute read floored at 2026-01-01 hit `not-found` on its last, narrow
        # window. Then as no progress: the same read, floored at 2026-02-16 07:01, paged
        # down to a candle at 07:05 and asked once more about the 3½ minutes below it —
        # the provider answered with that same 07:05 candle, which is no progress. Read
        # as an ending either way it set `history_ended`, which the archive stores as a
        # permanent boundary and uses to bulk-skip every older chunk still queued.
        if on_the_floor:
            reached_floor = True
        else:
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
