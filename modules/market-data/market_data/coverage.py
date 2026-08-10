"""What the archive has verified, as opposed to what it merely lacks.

Absence of a candle is ambiguous in the data itself. There is no candle for 3am on
Saturday because the market was shut, and no candle for last Tuesday afternoon because
ingest was down, and in a table of candles those two look exactly alike. A consumer
cannot tell a complete series from a holed one, and the module cannot tell which weekend
it has already asked the provider about — so it asks again, forever.

Coverage is the second record that resolves it: the stretches of time the archive has
actually looked at. Inside one, an empty period is an answer. Outside every one, it is a
question nobody has asked yet.

Ranges are stored merged. A fill writes a range per run, and left unmerged the table
grows a row per run until "is this moment covered" is a scan of thousands; merged, a
pair that has been collected continuously has one row.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

import asyncpg

from .models import CoverageRange, Resolution


class Absence(str, Enum):
    """Why there is no candle for a period.

    The distinction is the point of this module. `MARKET_CLOSED` is a complete answer —
    the archive looked and there was nothing to collect. `NOT_COLLECTED` is an admission,
    and the only one of the two worth sending anyone back to the provider for.
    """

    MARKET_CLOSED = "market_closed"
    NOT_COLLECTED = "not_collected"


# Serialises coverage writes for one pair. `hashtextextended` gives the bigint the
# advisory lock functions take, and the two-argument form keeps the symbol and the
# resolution from colliding through concatenation.
_LOCK_PAIR = "SELECT pg_advisory_xact_lock(hashtextextended($1 || ':' || $2, 0))"

# Overlapping *or* touching, so that two fills meeting end to end become one range rather
# than two that a lookup has to walk. `>=` on both sides is what makes touching count.
_OVERLAPPING = """
    SELECT range_start, range_end, history_ended, history_ends_at
      FROM coverage_ranges
     WHERE symbol = $1 AND resolution = $2
       AND range_start <= $4 AND range_end >= $3
     FOR UPDATE
"""

_DELETE_OVERLAPPING = """
    DELETE FROM coverage_ranges
     WHERE symbol = $1 AND resolution = $2
       AND range_start <= $4 AND range_end >= $3
"""

_INSERT = """
    INSERT INTO coverage_ranges
        (symbol, resolution, range_start, range_end, history_ended, history_ends_at)
    VALUES ($1, $2, $3, $4, $5, $6)
"""

_SELECT_ALL = """
    SELECT range_start, range_end, history_ended, history_ends_at
      FROM coverage_ranges
     WHERE symbol = $1 AND resolution = $2
     ORDER BY range_start
"""

_SELECT_COVERING = """
    SELECT 1
      FROM coverage_ranges
     WHERE symbol = $1 AND resolution = $2
       AND range_start <= $3 AND range_end >= $3
     LIMIT 1
"""

_SELECT_HISTORY_END = """
    SELECT history_ends_at
      FROM coverage_ranges
     WHERE symbol = $1 AND resolution = $2 AND history_ended
     LIMIT 1
"""

_DELETE_ALL = """
    DELETE FROM coverage_ranges WHERE symbol = $1 AND resolution = $2
"""

_CLEAR_HISTORY_END = """
    UPDATE coverage_ranges
       SET history_ended = false, history_ends_at = NULL
     WHERE symbol = $1 AND resolution = $2 AND history_ended
"""


async def record_coverage(
    conn: asyncpg.Connection,
    symbol: str,
    resolution: Resolution,
    start: datetime,
    end: datetime,
    history_ended: bool = False,
    history_ends_at: datetime | None = None,
) -> CoverageRange:
    """Record that a stretch of time has been verified, merged into what is already known.

    Returns the range as it now stands, which may be wider than the one passed in.

    `history_ended` says the provider has nothing older than `history_ends_at`, which is
    where the read that found it actually ran out — the oldest candle it brought back,
    never the edge it asked about. The two are a whole window apart, and the boundary is
    kept and acted on long after the window is forgotten.

    It carries its own point rather than borrowing `range_start` because ranges merge: a
    range meeting an older one end to end becomes one row starting at the older edge, and
    a boundary read off that start slides to wherever the pair's oldest coverage happens
    to begin. The flag survives a merge, and so does the earliest point any member named.
    """
    if history_ended and history_ends_at is None:
        raise ValueError(
            "a history boundary must say where it lies: pass the oldest candle the read "
            "returned, not the edge it asked about"
        )
    # Through the model first, so a naive datetime is refused here rather than stored as
    # whatever wall clock the writer happened to have — and so the ordering check below
    # compares two instants rather than an instant and a wall clock.
    offered = CoverageRange(
        symbol=symbol,
        resolution=resolution,
        range_start=start,
        range_end=end,
        history_ended=history_ended,
        history_ends_at=history_ends_at,
    )
    if offered.range_end < offered.range_start:
        raise ValueError(
            "a coverage range cannot end before it starts: "
            f"{offered.range_start.isoformat()} to {offered.range_end.isoformat()}"
        )

    # One transaction, and a lock on the pair inside it. Reading the neighbours and
    # replacing them with their union is read-then-write: two fills recording adjacent
    # ranges at the same moment would otherwise leave two rows that should have been one,
    # or collide on the "at most one history_ended per pair" index. Row locks cannot help
    # — the second fill's rows do not exist yet — so the lock is on the pair itself, and
    # it is released with the transaction.
    async with conn.transaction():
        await conn.execute(_LOCK_PAIR, symbol, resolution.value)
        neighbours = await conn.fetch(
            _OVERLAPPING, symbol, resolution.value, offered.range_start, offered.range_end
        )

        merged_start = min([offered.range_start, *(row["range_start"] for row in neighbours)])
        merged_end = max([offered.range_end, *(row["range_end"] for row in neighbours)])
        merged_history_ended = offered.history_ended or any(
            row["history_ended"] for row in neighbours
        )
        # The deepest boundary any member named. Two of them can only disagree by one
        # having been measured when the provider held less, and the earlier one is the
        # one that was demonstrated.
        boundaries = [
            point
            for point in (offered.history_ends_at, *(r["history_ends_at"] for r in neighbours))
            if point is not None
        ]
        merged_ends_at = min(boundaries) if boundaries else None

        if neighbours:
            await conn.execute(
                _DELETE_OVERLAPPING,
                symbol,
                resolution.value,
                offered.range_start,
                offered.range_end,
            )
        await conn.execute(
            _INSERT,
            symbol,
            resolution.value,
            merged_start,
            merged_end,
            merged_history_ended,
            merged_ends_at,
        )

    return CoverageRange(
        symbol=symbol,
        resolution=resolution,
        range_start=merged_start,
        range_end=merged_end,
        history_ended=merged_history_ended,
        history_ends_at=merged_ends_at,
    )


async def read_coverage(
    conn: asyncpg.Connection, symbol: str, resolution: Resolution
) -> list[CoverageRange]:
    """Everything verified for one pair, oldest first."""
    rows = await conn.fetch(_SELECT_ALL, symbol, resolution.value)
    return [
        CoverageRange(
            symbol=symbol,
            resolution=resolution,
            range_start=row["range_start"],
            range_end=row["range_end"],
            history_ended=row["history_ended"],
            history_ends_at=row["history_ends_at"],
        )
        for row in rows
    ]


async def is_covered(
    conn: asyncpg.Connection, symbol: str, resolution: Resolution, moment: datetime
) -> bool:
    """Whether the archive has looked at this moment for this pair."""
    return await conn.fetchval(_SELECT_COVERING, symbol, resolution.value, moment) is not None


async def absence_at(
    conn: asyncpg.Connection, symbol: str, resolution: Resolution, moment: datetime
) -> Absence:
    """Why there is no candle at `moment` — assuming the caller has established there
    isn't one.

    Takes no position on whether a candle exists, because the caller reading a range
    already knows which periods came back empty and asking the candle table again per
    empty period would be a query per hole.
    """
    if await is_covered(conn, symbol, resolution, moment):
        return Absence.MARKET_CLOSED
    return Absence.NOT_COLLECTED


async def delete_all_coverage(
    conn: asyncpg.Connection, symbol: str, resolution: Resolution
) -> None:
    """Remove every verified range for one pair.

    Coverage and candles must disappear together — a range that outlives its candles
    tells planning a period is already fetched when nothing is there
    (`market-data-store` spec, "Skasowanie danych pary zdejmuje też jej pokrycie"). The
    caller is the one holding both deletions in a single transaction; this function only
    ever does its own half.
    """
    await conn.execute(_DELETE_ALL, symbol, resolution.value)


async def earliest_reachable(
    conn: asyncpg.Connection, symbol: str, resolution: Resolution
) -> datetime | None:
    """Where the provider's history was last found to end, or `None` if nobody has
    reached it.

    Reported, not enforced. Planning stopped clipping against this: the clip only ever
    bit a request reaching deeper than the boundary, which is the one request that means
    "measure it again", and it bit silently — a pair whose boundary was recorded once
    could never be deepened afterwards. What still uses the boundary is the job that
    finds it, to settle in bulk the chunks queued behind it.

    `None` means the module has not yet reached the end of the provider's history — not
    that there is no limit.
    """
    return await conn.fetchval(_SELECT_HISTORY_END, symbol, resolution.value)


async def clear_history_boundary(
    conn: asyncpg.Connection, symbol: str, resolution: Resolution
) -> datetime | None:
    """Forget that the provider's history was ever found to end, keeping every candle and
    every verified range. Returns the boundary that was dropped, or `None` if there was
    none.

    The boundary exists to stop work nobody would return to, which is worth having and is
    also why it must be droppable. It is recorded from one answer on one day; capital.com
    deepens its own history over time, and an answer that was right in August is not an
    answer about today. Nothing else in this module clears it — deleting the pair used to
    be the only way, which is a price out of all proportion to re-asking a question.

    Called only by the path that actually orders collection. Reading coverage and pricing
    a job leave it alone (`market-data-store` spec, "Odczyt stanu pokrycia nie zmienia
    granicy"), so an operator can look without changing what they are looking at.
    """
    # Read before writing rather than RETURNING: the returning clause reports the row as
    # it now stands, which after this update is the null we just put there. One
    # transaction, because a boundary reported as dropped had better be dropped.
    async with conn.transaction():
        dropped = await conn.fetchval(_SELECT_HISTORY_END, symbol, resolution.value)
        await conn.execute(_CLEAR_HISTORY_END, symbol, resolution.value)
    return dropped


async def uncovered_within(
    conn: asyncpg.Connection,
    symbol: str,
    resolution: Resolution,
    start: datetime,
    end: datetime,
) -> list[tuple[datetime, datetime]]:
    """The stretches of `[start, end]` the archive has never looked at, oldest first.

    The complement of coverage, clipped to what was asked for. A consumer reading a range
    needs this beside the candles: a series with nothing in it on Saturday and a series
    with nothing in it because ingest was down are the same list of candles, and only one
    of them is complete.

    Empty means the whole requested range was verified — which is not the same as the
    range being full of candles.
    """
    if end < start:
        raise ValueError(
            f"a range cannot end before it starts: {start.isoformat()} to {end.isoformat()}"
        )

    gaps: list[tuple[datetime, datetime]] = []
    edge = start
    for covered in await read_coverage(conn, symbol, resolution):
        if covered.range_end < start:
            continue
        if covered.range_start > end:
            break
        if covered.range_start > edge:
            gaps.append((edge, min(covered.range_start, end)))
        edge = max(edge, covered.range_end)
        if edge >= end:
            return gaps

    if edge < end:
        gaps.append((edge, end))
    return gaps
