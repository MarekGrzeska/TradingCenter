from __future__ import annotations

from datetime import UTC, datetime, timedelta

import asyncpg
import pytest

from market_data.models import Candle, CandleSource, PriceSide, Resolution
from market_data.rollups import (
    DERIVABLE,
    bucket_start,
    minutes_per_period,
    read_derived,
    refresh,
    refresh_all,
)
from market_data.store import write_candles

MIDNIGHT = datetime(2026, 8, 7, 0, 0, tzinfo=UTC)


def minute(offset: int, **overrides) -> Candle:
    """One minute candle, `offset` minutes after midnight UTC."""
    base = float(offset)
    return Candle(
        **{
            "symbol": "US100",
            "resolution": Resolution.MINUTE,
            "period_start": MIDNIGHT + timedelta(minutes=offset),
            "open": 100.0 + base,
            "high": 100.5 + base,
            "low": 99.5 + base,
            "close": 100.2 + base,
            "volume": 10.0,
            "source": CandleSource.HISTORY,
            **overrides,
        }
    )


# --- the boundary, in Python (the SQL is checked against it below) ------------------


@pytest.mark.parametrize(
    ("resolution", "minutes"),
    [
        (Resolution.MINUTE_5, 5),
        (Resolution.MINUTE_15, 15),
        (Resolution.MINUTE_30, 30),
        (Resolution.HOUR, 60),
        (Resolution.HOUR_4, 240),
    ],
)
def test_a_period_holds_the_minutes_it_should(resolution: Resolution, minutes: int) -> None:
    assert minutes_per_period(resolution) == minutes


def test_every_derivable_resolution_divides_a_day() -> None:
    # Which is what makes UTC midnight the anchor for all of them, and what makes the
    # epoch a usable origin at all.
    from market_data.rollups import PERIOD_SECONDS

    assert all(86_400 % seconds == 0 for seconds in PERIOD_SECONDS.values())


def test_day_and_week_are_not_derivable() -> None:
    # Their boundary follows the venue's session, not the clock. A daily candle guessed
    # from UTC midnight looks right and is wrong — the gateway's forming candle skips
    # them for the same reason.
    assert Resolution.DAY not in DERIVABLE
    assert Resolution.WEEK not in DERIVABLE
    assert Resolution.MINUTE not in DERIVABLE  # the source, not a result


@pytest.mark.parametrize(
    ("at_minute", "resolution", "expected_minute"),
    [
        (7, Resolution.MINUTE_5, 5),
        (7, Resolution.MINUTE_15, 0),
        (44, Resolution.MINUTE_15, 30),
        (44, Resolution.MINUTE_30, 30),
        (44, Resolution.HOUR, 0),
        (301, Resolution.HOUR_4, 240),
    ],
)
def test_a_moment_falls_into_the_period_that_contains_it(
    at_minute: int, resolution: Resolution, expected_minute: int
) -> None:
    moment = MIDNIGHT + timedelta(minutes=at_minute)
    assert bucket_start(moment, resolution) == MIDNIGHT + timedelta(minutes=expected_minute)


def test_the_four_hour_boundary_is_utc_midnight() -> None:
    # Assumed here, verified against the provider in tests/test_live.py.
    for hour in (0, 4, 8, 12, 16, 20):
        start = MIDNIGHT + timedelta(hours=hour)
        assert bucket_start(start, Resolution.HOUR_4) == start
        assert bucket_start(start + timedelta(minutes=239), Resolution.HOUR_4) == start


# --- 5.5: what a derived candle is made of ------------------------------------------


@pytest.mark.db
async def test_a_derived_candle_opens_first_closes_last_and_spans_all(
    db: asyncpg.Connection,
) -> None:
    """The rule, stated once: open of the first, high and low of every one, close of the
    last. The extremes are put in the middle of the period on purpose, so a candle that
    merely copied the first and last minute would fail."""
    await write_candles(
        db,
        [
            minute(0, open=100.0, high=101.0, low=99.0, close=100.5),
            minute(1, open=100.5, high=140.0, low=100.0, close=120.0),  # the high
            minute(2, open=120.0, high=120.5, low=60.0, close=70.0),  # the low
            minute(3, open=70.0, high=80.0, low=70.0, close=75.0),
            minute(4, open=75.0, high=90.0, low=74.0, close=88.0),
        ],
    )

    await refresh(db, "US100", Resolution.MINUTE_5, MIDNIGHT, MIDNIGHT)

    [derived] = await read_derived(db, "US100", Resolution.MINUTE_5)
    assert derived.open == 100.0  # the first minute's open
    assert derived.high == 140.0  # the highest of all five
    assert derived.low == 60.0  # the lowest of all five
    assert derived.close == 88.0  # the last minute's close


@pytest.mark.db
async def test_a_derived_candle_starts_where_its_period_starts(db: asyncpg.Connection) -> None:
    await write_candles(db, [minute(m) for m in range(5, 10)])

    await refresh(db, "US100", Resolution.MINUTE_5, MIDNIGHT, MIDNIGHT + timedelta(minutes=10))

    starts = [c.period_start for c in await read_derived(db, "US100", Resolution.MINUTE_5)]
    assert starts == [MIDNIGHT + timedelta(minutes=5)]


@pytest.mark.db
async def test_minutes_out_of_order_do_not_confuse_the_edges(db: asyncpg.Connection) -> None:
    # The open and close are the first and last *by time*, not by arrival.
    await write_candles(
        db,
        [
            minute(2, open=3.0, close=30.0),
            minute(0, open=1.0, close=10.0),
            minute(1, open=2.0, close=20.0),
        ],
    )

    await refresh(db, "US100", Resolution.MINUTE_5, MIDNIGHT, MIDNIGHT)

    [derived] = await read_derived(db, "US100", Resolution.MINUTE_5)
    assert (derived.open, derived.close) == (1.0, 30.0)


@pytest.mark.db
async def test_volume_is_summed_when_every_minute_carried_one(db: asyncpg.Connection) -> None:
    await write_candles(db, [minute(m, volume=10.0) for m in range(5)])

    await refresh(db, "US100", Resolution.MINUTE_5, MIDNIGHT, MIDNIGHT)

    assert (await read_derived(db, "US100", Resolution.MINUTE_5))[0].volume == 50.0


@pytest.mark.db
async def test_volume_is_absent_when_any_minute_lacked_one(db: asyncpg.Connection) -> None:
    # A streamed candle never carries volume, so mixed periods are the normal case. A
    # partial sum would look exact and be understated.
    await write_candles(db, [minute(0, volume=None), *(minute(m) for m in range(1, 5))])

    await refresh(db, "US100", Resolution.MINUTE_5, MIDNIGHT, MIDNIGHT)

    assert (await read_derived(db, "US100", Resolution.MINUTE_5))[0].volume is None


@pytest.mark.db
async def test_a_derived_candle_keeps_the_price_side(db: asyncpg.Connection) -> None:
    await write_candles(db, [minute(m) for m in range(5)])

    await refresh(db, "US100", Resolution.MINUTE_5, MIDNIGHT, MIDNIGHT)

    assert (await read_derived(db, "US100", Resolution.MINUTE_5))[0].price_side is PriceSide.BID


# --- 5.4: the period that is not all there ------------------------------------------


@pytest.mark.db
async def test_a_full_period_says_it_is_complete(db: asyncpg.Connection) -> None:
    await write_candles(db, [minute(m) for m in range(5)])

    await refresh(db, "US100", Resolution.MINUTE_5, MIDNIGHT, MIDNIGHT)

    [derived] = await read_derived(db, "US100", Resolution.MINUTE_5)
    assert derived.minutes_present == 5
    assert derived.complete is True


@pytest.mark.db
async def test_a_period_built_from_part_of_itself_says_so(db: asyncpg.Connection) -> None:
    # This is the ordinary state of the newest bar on a chart. Refusing to build it would
    # leave the last bar missing; building it silently would let it pass for settled.
    await write_candles(db, [minute(m) for m in range(3)])

    await refresh(db, "US100", Resolution.MINUTE_5, MIDNIGHT, MIDNIGHT)

    [derived] = await read_derived(db, "US100", Resolution.MINUTE_5)
    assert derived.minutes_present == 3
    assert derived.complete is False


@pytest.mark.db
async def test_a_period_completes_when_its_remaining_minutes_arrive(
    db: asyncpg.Connection,
) -> None:
    await write_candles(db, [minute(m) for m in range(3)])
    await refresh(db, "US100", Resolution.MINUTE_5, MIDNIGHT, MIDNIGHT)

    await write_candles(db, [minute(3), minute(4)])
    await refresh(db, "US100", Resolution.MINUTE_5, MIDNIGHT, MIDNIGHT)

    [derived] = await read_derived(db, "US100", Resolution.MINUTE_5)
    assert derived.complete is True
    assert derived.close == minute(4).close


# --- 5.3: refreshing only what changed ----------------------------------------------


@pytest.mark.db
async def test_a_refresh_rebuilds_only_the_periods_in_its_window(
    db: asyncpg.Connection,
) -> None:
    await write_candles(db, [minute(m) for m in range(15)])

    rebuilt = await refresh(
        db, "US100", Resolution.MINUTE_5, MIDNIGHT, MIDNIGHT + timedelta(minutes=4)
    )

    # One five-minute period touched, not the three the archive holds minutes for.
    assert rebuilt == 1
    assert len(await read_derived(db, "US100", Resolution.MINUTE_5)) == 1


@pytest.mark.db
async def test_a_minute_in_the_middle_rebuilds_its_whole_period(
    db: asyncpg.Connection,
) -> None:
    # A minute at 12:07 belongs to a bucket starting at 12:05. Refreshing only from 12:07
    # would rebuild that bucket from a fifth of its rows and call it complete.
    await write_candles(db, [minute(m) for m in range(5, 10)])

    await refresh(
        db,
        "US100",
        Resolution.MINUTE_5,
        MIDNIGHT + timedelta(minutes=7),
        MIDNIGHT + timedelta(minutes=7),
    )

    [derived] = await read_derived(db, "US100", Resolution.MINUTE_5)
    assert derived.minutes_present == 5
    assert derived.period_start == MIDNIGHT + timedelta(minutes=5)


@pytest.mark.db
async def test_refreshing_again_replaces_rather_than_duplicates(
    db: asyncpg.Connection,
) -> None:
    await write_candles(db, [minute(m) for m in range(5)])

    await refresh(db, "US100", Resolution.MINUTE_5, MIDNIGHT, MIDNIGHT)
    await refresh(db, "US100", Resolution.MINUTE_5, MIDNIGHT, MIDNIGHT)

    assert len(await read_derived(db, "US100", Resolution.MINUTE_5)) == 1


@pytest.mark.db
async def test_a_period_whose_minutes_are_gone_leaves_no_derived_candle(
    db: asyncpg.Connection,
) -> None:
    # An upsert alone would leave the stale candle in place forever, because an aggregate
    # over nothing produces no row to overwrite it with.
    await write_candles(db, [minute(m) for m in range(5)])
    await refresh(db, "US100", Resolution.MINUTE_5, MIDNIGHT, MIDNIGHT)
    assert len(await read_derived(db, "US100", Resolution.MINUTE_5)) == 1

    await db.execute("DELETE FROM candles")
    await refresh(db, "US100", Resolution.MINUTE_5, MIDNIGHT, MIDNIGHT)

    assert await read_derived(db, "US100", Resolution.MINUTE_5) == []


@pytest.mark.db
async def test_a_refresh_leaves_neighbouring_periods_alone(db: asyncpg.Connection) -> None:
    await write_candles(db, [minute(m) for m in range(10)])
    await refresh(db, "US100", Resolution.MINUTE_5, MIDNIGHT, MIDNIGHT + timedelta(minutes=9))
    assert len(await read_derived(db, "US100", Resolution.MINUTE_5)) == 2

    await db.execute("DELETE FROM candles WHERE period_start >= $1", MIDNIGHT + timedelta(minutes=5))
    await refresh(db, "US100", Resolution.MINUTE_5, MIDNIGHT, MIDNIGHT)

    # The second period's minutes are gone but its window was not refreshed, so its
    # derived candle is untouched — stale by design, until something refreshes it.
    assert len(await read_derived(db, "US100", Resolution.MINUTE_5)) == 2


@pytest.mark.db
async def test_a_window_that_ends_before_it_starts_is_refused(db: asyncpg.Connection) -> None:
    with pytest.raises(ValueError, match="cannot end before"):
        await refresh(db, "US100", Resolution.MINUTE_5, MIDNIGHT + timedelta(minutes=5), MIDNIGHT)


# --- 5.2: every derivable resolution --------------------------------------------------


@pytest.mark.db
async def test_one_pass_builds_every_derivable_resolution(db: asyncpg.Connection) -> None:
    # Four hours of minutes: one HOUR_4 period exactly, and whole numbers of every
    # shorter one.
    await write_candles(db, [minute(m) for m in range(240)])

    rebuilt = await refresh_all(db, "US100", MIDNIGHT, MIDNIGHT + timedelta(minutes=239))

    assert rebuilt == {
        Resolution.MINUTE_5: 48,
        Resolution.MINUTE_15: 16,
        Resolution.MINUTE_30: 8,
        Resolution.HOUR: 4,
        Resolution.HOUR_4: 1,
    }


@pytest.mark.db
async def test_the_four_hour_candle_spans_its_four_hours(db: asyncpg.Connection) -> None:
    await write_candles(db, [minute(m) for m in range(240)])

    await refresh(db, "US100", Resolution.HOUR_4, MIDNIGHT, MIDNIGHT + timedelta(minutes=239))

    [derived] = await read_derived(db, "US100", Resolution.HOUR_4)
    assert derived.period_start == MIDNIGHT
    assert derived.minutes_present == 240
    assert derived.complete is True
    assert derived.open == minute(0).open
    assert derived.close == minute(239).close


@pytest.mark.db
async def test_derived_candles_read_back_oldest_first(db: asyncpg.Connection) -> None:
    await write_candles(db, [minute(m) for m in range(15)])
    await refresh(db, "US100", Resolution.MINUTE_5, MIDNIGHT, MIDNIGHT + timedelta(minutes=14))

    starts = [c.period_start for c in await read_derived(db, "US100", Resolution.MINUTE_5)]
    assert starts == sorted(starts)
    assert len(starts) == 3


@pytest.mark.db
async def test_a_derived_read_excludes_its_end(db: asyncpg.Connection) -> None:
    await write_candles(db, [minute(m) for m in range(15)])
    await refresh(db, "US100", Resolution.MINUTE_5, MIDNIGHT, MIDNIGHT + timedelta(minutes=14))

    got = await read_derived(
        db, "US100", Resolution.MINUTE_5, MIDNIGHT, MIDNIGHT + timedelta(minutes=10)
    )
    assert [c.period_start for c in got] == [MIDNIGHT, MIDNIGHT + timedelta(minutes=5)]


@pytest.mark.db
async def test_derivation_is_kept_per_pair(db: asyncpg.Connection) -> None:
    await write_candles(db, [minute(m) for m in range(5)])
    await write_candles(db, [minute(m, symbol="GOLD") for m in range(5)])

    await refresh(db, "US100", Resolution.MINUTE_5, MIDNIGHT, MIDNIGHT)

    assert len(await read_derived(db, "US100", Resolution.MINUTE_5)) == 1
    assert await read_derived(db, "GOLD", Resolution.MINUTE_5) == []


@pytest.mark.db
async def test_only_minute_candles_are_a_source(db: asyncpg.Connection) -> None:
    # A pair tracked at HOUR_4 directly puts provider candles in `candles` at that
    # resolution. They are observations, not ingredients, and must not be folded in.
    await write_candles(db, [minute(m) for m in range(5)])
    await write_candles(
        db,
        [
            Candle(
                symbol="US100",
                resolution=Resolution.HOUR,
                period_start=MIDNIGHT,
                open=1.0,
                high=1.0,
                low=1.0,
                close=1.0,
                source=CandleSource.HISTORY,
            )
        ],
    )

    await refresh(db, "US100", Resolution.MINUTE_5, MIDNIGHT, MIDNIGHT)

    assert (await read_derived(db, "US100", Resolution.MINUTE_5))[0].minutes_present == 5
