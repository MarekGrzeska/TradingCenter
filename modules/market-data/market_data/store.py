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
from datetime import datetime

import asyncpg

from .models import Candle, CandleSource, PriceSide, Resolution


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


async def write_candles(conn: asyncpg.Connection, candles: Iterable[Candle]) -> int:
    """Store closed candles, overwriting what is already held for the same period.

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
