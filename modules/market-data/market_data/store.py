"""Reading and writing candles — the only door to the candle table.

Two rules live here rather than in whatever calls it. A candle still being built never
reaches storage, and writing a period that is already stored overwrites it instead of
adding a second row. Both are properties of the archive, not of any one caller, so both
are enforced where every caller passes.

Queries go through asyncpg directly. SQLAlchemy is present for alembic and stops at the
migrations; the runtime path has no ORM in it.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime

import asyncpg

from .models import Candle, CandleSource, PriceSide, Resolution


class FormingCandleRejected(ValueError):
    """A caller offered a candle that has not closed yet.

    Raised rather than ignored. A forming candle in a write is a caller reading its own
    source wrong, and a silent drop turns that into a gap discovered weeks later, when
    the provider no longer has the data to fill it.
    """


# ON CONFLICT rather than a read-then-write: the same period can arrive from the stream
# and from a backfill at the same time, and two statements would race into a duplicate-key
# error or a lost value depending on which won.
_UPSERT = """
    INSERT INTO candles (
        symbol, resolution, period_start, price_side,
        open, high, low, close, volume, source, recorded_at
    )
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, now())
    ON CONFLICT (symbol, resolution, period_start) DO UPDATE SET
        price_side  = EXCLUDED.price_side,
        open        = EXCLUDED.open,
        high        = EXCLUDED.high,
        low         = EXCLUDED.low,
        close       = EXCLUDED.close,
        volume      = EXCLUDED.volume,
        source      = EXCLUDED.source,
        recorded_at = EXCLUDED.recorded_at
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


async def write_candles(conn: asyncpg.Connection, candles: Iterable[Candle]) -> int:
    """Store closed candles, overwriting any already held for the same period.

    Returns how many were written. Raises `FormingCandleRejected` if any candle in the
    batch is still forming — and writes none of them, because a partially applied batch
    leaves the caller with no way to know which half landed.
    """
    rows = []
    for candle in candles:
        if candle.forming:
            raise FormingCandleRejected(
                f"{candle.symbol} {candle.resolution.value} at "
                f"{candle.period_start.isoformat()} is still forming; only closed candles "
                "are stored"
            )
        rows.append(
            (
                candle.symbol,
                candle.resolution.value,
                candle.period_start,
                candle.price_side.value,
                candle.open,
                candle.high,
                candle.low,
                candle.close,
                candle.volume,
                candle.source.value,
            )
        )

    if not rows:
        return 0

    await conn.executemany(_UPSERT, rows)
    return len(rows)


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
