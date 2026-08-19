"""Reading and writing candles — the only door to the candle table.

Three rules live here rather than in whatever calls it. A candle still being built never
reaches storage. Writing a period that is already stored overwrites it instead of adding
a second row. And when the two roads disagree about a period, the value read from the
provider's history wins over the one that came off the stream. All three are properties
of the archive rather than of any one caller, so all three are enforced where every
caller passes.

Queries go through asyncpg directly. SQLAlchemy is present for alembic and stops at the
migrations; the runtime path has no ORM in it.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime

import asyncpg

from .coverage import record_coverage
from .db import fetch_one
from .models import Candle, CandleSource, CoverageRange, PriceSide, Resolution
from .rollups import refresh_all


class FormingCandleRejected(ValueError):
    """A caller offered a candle that has not closed yet.

    Raised rather than ignored. A forming candle in a write is a caller reading its own
    source wrong, and a silent drop turns that into a gap discovered weeks later, when
    the provider no longer has the data to fill it.
    """


# One statement for a whole batch, and ON CONFLICT rather than a read-then-write: the
# same period can arrive from the stream and from a backfill at the same moment, and two
# statements would race into either a duplicate-key error or a lost value, depending on
# which got there first.
#
# The WHERE on the update is the authority rule. A history read watched the period whole;
# a stream that was disconnected for part of it reports a range that is too narrow and a
# volume it never saw. So a streamed value may not overwrite a stored history one — every
# other combination may, including history over history, because a refetch is the
# provider correcting itself.
#
# RETURNING makes the count honest: a row the rule declined to update returns nothing,
# and a caller reporting progress needs "written" to mean written.
_UPSERT = """
    INSERT INTO candles (
        symbol, resolution, period_start, price_side,
        open, high, low, close, volume, source
    )
    SELECT * FROM unnest(
        $1::text[], $2::text[], $3::timestamptz[], $4::text[],
        $5::float8[], $6::float8[], $7::float8[], $8::float8[], $9::float8[], $10::text[]
    )
    ON CONFLICT (symbol, resolution, period_start) DO UPDATE SET
        price_side  = EXCLUDED.price_side,
        open        = EXCLUDED.open,
        high        = EXCLUDED.high,
        low         = EXCLUDED.low,
        close       = EXCLUDED.close,
        volume      = EXCLUDED.volume,
        source      = EXCLUDED.source,
        recorded_at = now()
    WHERE NOT (candles.source = 'history' AND EXCLUDED.source = 'stream')
    RETURNING 1
"""

_SELECT_LATEST = """
    SELECT max(period_start) FROM candles WHERE symbol = $1 AND resolution = $2
"""

_SELECT_RECENT = """
    SELECT symbol, resolution, period_start, price_side,
           open, high, low, close, volume, source
      FROM candles
     WHERE symbol = $1 AND resolution = $2
     ORDER BY period_start DESC
     LIMIT $3
"""

_SELECT_RANGE = """
    SELECT symbol, resolution, period_start, price_side,
           open, high, low, close, volume, source
      FROM candles
     WHERE symbol = $1
       AND resolution = $2
       AND ($3::timestamptz IS NULL OR period_start >= $3)
       AND ($4::timestamptz IS NULL OR period_start < $4)
     ORDER BY period_start
"""

_SELECT_BOUNDS = """
    SELECT count(*) AS removed, min(period_start) AS earliest, max(period_start) AS latest
      FROM candles
     WHERE symbol = $1 AND resolution = $2
"""

_DELETE_ALL = """
    DELETE FROM candles WHERE symbol = $1 AND resolution = $2
"""


async def write_candles(conn: asyncpg.Connection, candles: Iterable[Candle]) -> int:
    """Store closed candles, overwriting what is already held for the same period.

    The statement and nothing else — no coverage, no rollups. Ingest goes through
    `commit_candles`, which is the only caller of this in the module and the only one a
    test allows (`test_ingest.py::test_nothing_but_the_store_writes_candles_on_its_own`);
    the tests that reach for this directly are seeding rows, not ingesting them.

    Returns how many rows the archive actually took — which is not always how many were
    offered, because a streamed value never displaces a stored history one.

    Raises `FormingCandleRejected` if any candle in the batch is still forming, and
    writes none of them: a partially applied batch leaves the caller with no way to know
    which half landed.
    """
    # Keyed by the triple, keeping the last offer for each. Postgres refuses an
    # ON CONFLICT that would touch the same row twice in one statement, and a batch is
    # normally one source at a time anyway, so last-one-wins matches what a caller means
    # by sending the same period twice.
    kept: dict[tuple[str, str, datetime], Candle] = {}
    for candle in candles:
        if candle.forming:
            raise FormingCandleRejected(
                f"{candle.symbol} {candle.resolution.value} at "
                f"{candle.period_start.isoformat()} is still forming; only closed candles "
                "are stored"
            )
        kept[(candle.symbol, candle.resolution.value, candle.period_start)] = candle

    if not kept:
        return 0

    rows = list(kept.values())
    written = await conn.fetch(
        _UPSERT,
        [c.symbol for c in rows],
        [c.resolution.value for c in rows],
        [c.period_start for c in rows],
        [c.price_side.value for c in rows],
        [c.open for c in rows],
        [c.high for c in rows],
        [c.low for c in rows],
        [c.close for c in rows],
        [c.volume for c in rows],
        [c.source.value for c in rows],
    )
    return len(written)


@dataclass(frozen=True)
class Committed:
    """What one ingest write did: how many rows the archive took, and the coverage range
    as it stands after the stretch was merged into it."""

    written: int
    coverage: CoverageRange


async def commit_candles(
    conn: asyncpg.Connection,
    candles: Sequence[Candle],
    *,
    symbol: str,
    resolution: Resolution,
    covered_from: datetime,
    covered_to: datetime,
    history_ended: bool = False,
    history_ends_at: datetime | None = None,
) -> Committed:
    """The one way candles enter the archive: stored, the stretch recorded as verified,
    and the rollups rebuilt over what arrived.

    Three call sites wrote those three steps out by hand — the stream, a gap fill and a
    collection job's chunk — and all three had to agree about the two that are not the
    write. Missing the coverage row leaves a stretch that was read reporting as never
    collected, which sends the same request again tomorrow and every day after; missing
    the rollup refresh leaves every derived resolution a period behind its own minutes,
    with nothing to say so. Neither failure is visible at the call site that caused it,
    and neither reddens a test of the write.

    Coverage is recorded whether or not anything was written: an exhaustive read of an
    empty stretch is still a stretch looked at (`jobs/runner.py` depends on exactly
    that). The rollups are refreshed over what *arrived* rather than what was taken,
    because the authority rule can decline a streamed value over a stored history one
    and the derived candle still has to be rebuilt from the minutes that are there.

    `candles` is assumed oldest-first, which every caller's own filtering already gives
    it — the range handed to `refresh_all` is its first and last.
    """
    written = await write_candles(conn, candles) if candles else 0
    coverage = await record_coverage(
        conn,
        symbol,
        resolution,
        covered_from,
        covered_to,
        history_ended=history_ended,
        history_ends_at=history_ends_at,
    )
    if candles and resolution is Resolution.MINUTE:
        await refresh_all(conn, symbol, candles[0].period_start, candles[-1].period_start)
    return Committed(written=written, coverage=coverage)


async def read_candles(
    conn: asyncpg.Connection,
    symbol: str,
    resolution: Resolution,
    start: datetime | None = None,
    end: datetime | None = None,
) -> Sequence[Candle]:
    """Candles for one pair, oldest first.

    The window is half-open — `start` included, `end` excluded — so two adjacent reads
    join without repeating the candle on the seam.
    """
    rows = await conn.fetch(_SELECT_RANGE, symbol, resolution.value, start, end)
    return [
        Candle(
            symbol=row["symbol"],
            resolution=Resolution(row["resolution"]),
            period_start=row["period_start"],
            price_side=PriceSide(row["price_side"]),
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            volume=row["volume"],
            source=CandleSource(row["source"]),
        )
        for row in rows
    ]


async def read_latest_period(
    conn: asyncpg.Connection, symbol: str, resolution: Resolution
) -> datetime | None:
    """The newest period this pair holds, or `None` if it holds nothing.

    What ingest asks before deciding whether to reach for anything: it is the right edge
    of the gap, and its absence means there is no edge because there is no data.
    """
    return await conn.fetchval(_SELECT_LATEST, symbol, resolution.value)


async def delete_all_candles(
    conn: asyncpg.Connection, symbol: str, resolution: Resolution
) -> tuple[int, datetime | None, datetime | None]:
    """Remove every candle stored for one pair — deliberate, and total.

    Returns how many were removed and the oldest and newest `period_start` among them
    (both `None` when there was nothing to remove), which is what a caller records as
    the range that just disappeared. There is no partial form of this: a pair either
    keeps every candle or none, per `market-data-tracking` spec, "Skasowanie pary
    zatrzymuje zbieranie i usuwa jej dane".
    """
    row = await fetch_one(conn, _SELECT_BOUNDS, symbol, resolution.value)
    removed, earliest, latest = row["removed"], row["earliest"], row["latest"]
    if removed:
        await conn.execute(_DELETE_ALL, symbol, resolution.value)
    return removed, earliest, latest


async def read_recent(
    conn: asyncpg.Connection, symbol: str, resolution: Resolution, limit: int
) -> Sequence[Candle]:
    """The newest `limit` candles, still oldest first.

    What a snapshot is made of. Ordered descending to pick the tail, then turned back
    round, because a consumer charting this wants time increasing however few it asked
    for.
    """
    rows = await conn.fetch(_SELECT_RECENT, symbol, resolution.value, limit)
    return [
        Candle(
            symbol=row["symbol"],
            resolution=Resolution(row["resolution"]),
            period_start=row["period_start"],
            price_side=PriceSide(row["price_side"]),
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            volume=row["volume"],
            source=CandleSource(row["source"]),
        )
        for row in reversed(rows)
    ]
