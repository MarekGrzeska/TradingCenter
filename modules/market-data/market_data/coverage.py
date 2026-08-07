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
    SELECT range_start, range_end, history_ended
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
    INSERT INTO coverage_ranges (symbol, resolution, range_start, range_end, history_ended)
    VALUES ($1, $2, $3, $4, $5)
"""

_SELECT_ALL = """
    SELECT range_start, range_end, history_ended
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
    SELECT range_start
      FROM coverage_ranges
     WHERE symbol = $1 AND resolution = $2 AND history_ended
     LIMIT 1
"""


async def record_coverage(
    conn: asyncpg.Connection,
    symbol: str,
    resolution: Resolution,
    start: datetime,
    end: datetime,
    history_ended: bool = False,
) -> CoverageRange:
    """Record that a stretch of time has been verified, merged into what is already known.

    Returns the range as it now stands, which may be wider than the one passed in.

    `history_ended` says the provider has nothing older than `start`. It survives a merge
    because nothing can ever be older than it — a range starting before the provider's
    own first candle is not something backfill can produce — so the merged range's start
    is that boundary whenever any member carried it.
    """
    # Through the model first, so a naive datetime is refused here rather than stored as
    # whatever wall clock the writer happened to have — and so the ordering check below
    # compares two instants rather than an instant and a wall clock.
    offered = CoverageRange(
        symbol=symbol,
        resolution=resolution,
        range_start=start,
        range_end=end,
        history_ended=history_ended,
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

        if neighbours:
            await conn.execute(
                _DELETE_OVERLAPPING,
                symbol,
                resolution.value,
                offered.range_start,
                offered.range_end,
            )
        await conn.execute(
            _INSERT, symbol, resolution.value, merged_start, merged_end, merged_history_ended
        )

    return CoverageRange(
        symbol=symbol,
        resolution=resolution,
        range_start=merged_start,
        range_end=merged_end,
        history_ended=merged_history_ended,
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


async def earliest_reachable(
    conn: asyncpg.Connection, symbol: str, resolution: Resolution
) -> datetime | None:
    """The oldest moment worth asking the provider about, or `None` if that is unknown.

    This is the `history_ended` boundary, and it is what stops backfill from walking
    further back every night into data that was never there. `None` means the module has
    not yet reached the end of the provider's history — not that there is no limit.
    """
    return await conn.fetchval(_SELECT_HISTORY_END, symbol, resolution.value)


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
