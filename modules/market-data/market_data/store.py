"""Reading and writing candles — the only door to the candle table. Three rules live here because they
are properties of the archive: no forming candle, one row per period, and history outranks the stream."""

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
    """A caller offered a candle that has not closed yet. Raised rather than ignored: a silent drop
    turns a caller's bug into a gap discovered weeks later, when the provider no longer has the data."""


# ON CONFLICT rather than read-then-write: the same period can arrive from the stream and a backfill
# at once. The WHERE on the update is the authority rule — a streamed value never displaces a stored
# history one, since a disconnected stream understates the range it reports.
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
    """Store closed candles, overwriting what is held for the same period, and return how many the
    archive took. Raises on a forming candle and writes none of the batch, so no half lands."""
    # Keyed by the triple, keeping the last offer for each: Postgres refuses an ON CONFLICT that
    # would touch the same row twice in one statement.
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
    """The one way candles enter the archive: stored, the stretch recorded as verified, and the rollups
    rebuilt over what *arrived* — three steps three call sites used to write out and have to agree on."""
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
    """Candles for one pair, oldest first. The window is half-open, so two adjacent reads join without
    repeating the candle on the seam."""
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
    """The newest period this pair holds, or `None`. The right edge of the gap ingest asks about, and
    its absence means there is no edge because there is no data."""
    return await conn.fetchval(_SELECT_LATEST, symbol, resolution.value)


async def delete_all_candles(
    conn: asyncpg.Connection, symbol: str, resolution: Resolution
) -> tuple[int, datetime | None, datetime | None]:
    """Remove every candle stored for one pair — deliberate, and total. Returns the count and the range
    that disappeared; there is no partial form of this."""
    row = await fetch_one(conn, _SELECT_BOUNDS, symbol, resolution.value)
    removed, earliest, latest = row["removed"], row["earliest"], row["latest"]
    if removed:
        await conn.execute(_DELETE_ALL, symbol, resolution.value)
    return removed, earliest, latest


async def read_recent(
    conn: asyncpg.Connection, symbol: str, resolution: Resolution, limit: int
) -> Sequence[Candle]:
    """The newest `limit` candles, still oldest first. Ordered descending to pick the tail, then turned
    back round, because a consumer charting this wants time increasing."""
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
