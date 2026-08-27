"""Derived resolutions, built from the minute series, because eight separate fetches cost eight times
the traffic. Not a materialized view: `REFRESH` recomputes the whole archive to settle one bar."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import asyncpg
from pydantic import BaseModel

from .models import PriceSide, Resolution
from .periods import PERIOD_SECONDS

# The resolutions whose period may be floored by arithmetic on the epoch. MINUTE is the source; DAY
# and WEEK follow the venue's session, and a candle floored to UTC midnight looks right and is wrong.
DERIVABLE = (
    Resolution.MINUTE_5,
    Resolution.MINUTE_15,
    Resolution.MINUTE_30,
    Resolution.HOUR,
    Resolution.HOUR_4,
)

# The epoch, and therefore UTC midnight, because every period above divides a day evenly. Spelled
# into the SQL so the anchor this module depends on is visible in the statement that depends on it.
BUCKET_ORIGIN = "1970-01-01 00:00:00+00"


class DerivedCandle(BaseModel):
    """A candle nobody observed, and which says so."""

    symbol: str
    resolution: Resolution
    period_start: datetime
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None
    price_side: PriceSide = PriceSide.BID
    minutes_present: int
    # False when the archive held fewer minute candles than the period can hold — the ordinary state
    # of the newest bar, and also what a gap in the minute series looks like.
    complete: bool


def minutes_per_period(resolution: Resolution) -> int:
    """How many minute candles a complete period of `resolution` holds."""
    return PERIOD_SECONDS[resolution] // 60


def bucket_start(moment: datetime, resolution: Resolution) -> datetime:
    """The start of the period `moment` falls in — the same arithmetic the SQL does. Kept in Python for
    callers deciding which buckets to refresh, not for building candles."""
    if resolution not in DERIVABLE:
        # `PERIOD_SECONDS` carries a length for DAY and WEEK because overstating a period is safe
        # for sizing and staleness. Flooring is not: it would put a daily candle on UTC midnight.
        raise ValueError(
            f"{resolution.value} has no arithmetic period boundary; it comes from the provider"
        )
    step = PERIOD_SECONDS[resolution]
    seconds = int(moment.astimezone(UTC).timestamp())
    return datetime.fromtimestamp(seconds - seconds % step, tz=UTC)


# Aggregated in SQL rather than read into Python: a four-hour bucket is 240 minute rows. Grouping by
# price_side rather than assuming it, so a second side ever stored fails loudly on the primary key.
_REFRESH = """
    INSERT INTO derived_candles (
        symbol, resolution, period_start, price_side,
        open, high, low, close, volume, minutes_present, complete, derived_at
    )
    SELECT
        symbol,
        $2 AS resolution,
        date_bin($3::interval, period_start, TIMESTAMPTZ '{origin}') AS bucket,
        price_side,
        (array_agg(open ORDER BY period_start))[1],
        max(high),
        min(low),
        (array_agg(close ORDER BY period_start DESC))[1],
        -- Only when every contributing minute carried one. `sum` would otherwise skip the
        -- nulls and hand back a total that is understated and looks exact — and a stream
        -- candle never carries volume at all, so mixed periods are the normal case.
        CASE WHEN count(volume) = count(*) THEN sum(volume) END,
        count(*),
        count(*) = $4,
        now()
      FROM candles
     WHERE symbol = $1
       AND resolution = 'MINUTE'
       AND period_start >= $5
       AND period_start < $6
     GROUP BY symbol, bucket, price_side
    ON CONFLICT (symbol, resolution, period_start) DO UPDATE SET
        price_side      = EXCLUDED.price_side,
        open            = EXCLUDED.open,
        high            = EXCLUDED.high,
        low             = EXCLUDED.low,
        close           = EXCLUDED.close,
        volume          = EXCLUDED.volume,
        minutes_present = EXCLUDED.minutes_present,
        complete        = EXCLUDED.complete,
        derived_at      = EXCLUDED.derived_at
    RETURNING 1
"""

_SELECT_RANGE = """
    SELECT symbol, resolution, period_start, price_side,
           open, high, low, close, volume, minutes_present, complete
      FROM derived_candles
     WHERE symbol = $1
       AND resolution = $2
       AND ($3::timestamptz IS NULL OR period_start >= $3)
       AND ($4::timestamptz IS NULL OR period_start < $4)
     ORDER BY period_start
"""

_DELETE_RANGE = """
    DELETE FROM derived_candles
     WHERE symbol = $1
       AND resolution = $2
       AND period_start >= $3
       AND period_start < $4
"""

_DELETE_ALL_FOR_SYMBOL = """
    DELETE FROM derived_candles WHERE symbol = $1
"""


async def refresh(
    conn: asyncpg.Connection,
    symbol: str,
    resolution: Resolution,
    since: datetime,
    until: datetime,
) -> int:
    """Rebuild every derived period touched by minute candles in `[since, until)`, and return how many.
    The window is widened to whole periods, or a minute at 12:07 rebuilds its bucket from a seventh."""
    if until < since:
        raise ValueError(
            f"a refresh window cannot end before it starts: "
            f"{since.isoformat()} to {until.isoformat()}"
        )

    step = PERIOD_SECONDS[resolution]
    window_start = bucket_start(since, resolution)
    # The bucket `until` falls in is included whole: a period is rebuilt from all of the
    # minutes the archive holds for it, not from the ones this particular write brought.
    window_end = bucket_start(until, resolution) + timedelta(seconds=step)

    # Cleared before it is rebuilt, in one transaction. An upsert alone would leave behind any period
    # whose minute candles have since gone, sitting in the series forever looking like data.
    async with conn.transaction():
        await conn.execute(_DELETE_RANGE, symbol, resolution.value, window_start, window_end)
        rebuilt = await conn.fetch(
            _REFRESH.format(origin=BUCKET_ORIGIN),
            symbol,
            resolution.value,
            timedelta(seconds=step),
            minutes_per_period(resolution),
            window_start,
            window_end,
        )

    return len(rebuilt)


async def refresh_all(
    conn: asyncpg.Connection, symbol: str, since: datetime, until: datetime
) -> dict[Resolution, int]:
    """The same, for every resolution the minute series implies."""
    return {
        resolution: await refresh(conn, symbol, resolution, since, until)
        for resolution in DERIVABLE
    }


async def delete_all_for_symbol(conn: asyncpg.Connection, symbol: str) -> None:
    """Remove every rollup built from one symbol's minute series, across all of `DERIVABLE` at once.
    A rollup left behind would answer a derived read from data the operator just removed."""
    await conn.execute(_DELETE_ALL_FOR_SYMBOL, symbol)


async def read_derived(
    conn: asyncpg.Connection,
    symbol: str,
    resolution: Resolution,
    start: datetime | None = None,
    end: datetime | None = None,
) -> Sequence[DerivedCandle]:
    """Derived candles for one pair, oldest first, `end` excluded."""
    rows = await conn.fetch(_SELECT_RANGE, symbol, resolution.value, start, end)
    return [
        DerivedCandle(
            symbol=row["symbol"],
            resolution=Resolution(row["resolution"]),
            period_start=row["period_start"],
            price_side=PriceSide(row["price_side"]),
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            volume=row["volume"],
            minutes_present=row["minutes_present"],
            complete=row["complete"],
        )
        for row in rows
    ]
