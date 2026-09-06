from __future__ import annotations

from datetime import UTC, datetime, timedelta

import asyncpg
import pytest

from market_data.models import Candle, CandleSource, PriceSide, Resolution
from market_data.store import FormingCandleRejected, read_candles, write_candles

MOMENT = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)


def candle(**overrides) -> Candle:
    return Candle(
        **{
            "symbol": "US100",
            "resolution": Resolution.MINUTE,
            "period_start": MOMENT,
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 1_000.0,
            "source": CandleSource.STREAM,
            **overrides,
        }
    )



def test_a_candle_is_closed_unless_it_says_otherwise() -> None:
    assert candle().forming is False


def test_a_candle_is_stored_on_the_bid_side_unless_told_otherwise() -> None:
    assert candle().price_side is PriceSide.BID


def test_a_period_start_without_a_timezone_is_refused() -> None:
    # A naive datetime is read as local time by nearly everything downstream, which puts
    # the candle an hour or two off — silently, and only for part of the year.
    with pytest.raises(ValueError, match="naive"):
        candle(period_start=datetime(2026, 8, 7, 12, 0))  # noqa: DTZ001 - the point of the test


def test_a_period_start_in_another_zone_becomes_the_same_instant_in_utc() -> None:
    same_instant_elsewhere = datetime(2026, 8, 7, 14, 0, tzinfo=UTC).astimezone()
    assert candle(period_start=same_instant_elsewhere).period_start == datetime(
        2026, 8, 7, 14, 0, tzinfo=UTC
    )



@pytest.mark.db
async def test_writing_the_same_triple_twice_overwrites_rather_than_duplicates(
    db: asyncpg.Connection,
) -> None:
    await write_candles(db, [candle(close=100.5)])
    await write_candles(db, [candle(close=123.0)])

    stored = await read_candles(db, "US100", Resolution.MINUTE)
    assert len(stored) == 1
    assert stored[0].close == 123.0


@pytest.mark.db
async def test_a_repeated_write_does_not_repeat_a_timestamp_in_a_range_read(
    db: asyncpg.Connection,
) -> None:
    await write_candles(db, [candle(), candle(period_start=MOMENT + timedelta(minutes=1))])
    await write_candles(db, [candle()])

    stored = await read_candles(db, "US100", Resolution.MINUTE)
    timestamps = [c.period_start for c in stored]
    assert timestamps == sorted(set(timestamps))
    assert len(timestamps) == 2


@pytest.mark.db
async def test_the_same_period_from_the_other_source_is_still_one_candle(
    db: asyncpg.Connection,
) -> None:
    # A period reached by the stream and then by a backfill is one period. Which value
    # wins is a separate rule; that there is one row is this one.
    await write_candles(db, [candle(source=CandleSource.STREAM)])
    await write_candles(db, [candle(source=CandleSource.HISTORY)])

    stored = await read_candles(db, "US100", Resolution.MINUTE)
    assert len(stored) == 1
    assert stored[0].source is CandleSource.HISTORY



@pytest.mark.db
async def test_a_backfill_replaces_what_the_stream_left(db: asyncpg.Connection) -> None:
    # The stream may have been disconnected for part of the period, which understates the
    # range and loses the volume it never saw. A history read watched the whole period.
    await write_candles(db, [candle(source=CandleSource.STREAM, high=101.0, volume=None)])
    await write_candles(db, [candle(source=CandleSource.HISTORY, high=105.0, volume=2_000.0)])

    [stored] = await read_candles(db, "US100", Resolution.MINUTE)
    assert stored.source is CandleSource.HISTORY
    assert stored.high == 105.0
    assert stored.volume == 2_000.0


@pytest.mark.db
async def test_the_stream_does_not_displace_a_backfilled_value(db: asyncpg.Connection) -> None:
    # The same period arriving the other way round. The stored value stays put, because
    # the one now being offered is the weaker witness regardless of which came second.
    await write_candles(db, [candle(source=CandleSource.HISTORY, high=105.0, volume=2_000.0)])
    await write_candles(db, [candle(source=CandleSource.STREAM, high=101.0, volume=None)])

    [stored] = await read_candles(db, "US100", Resolution.MINUTE)
    assert stored.source is CandleSource.HISTORY
    assert stored.high == 105.0
    assert stored.volume == 2_000.0


@pytest.mark.db
async def test_a_refetch_corrects_an_earlier_refetch(db: asyncpg.Connection) -> None:
    # History over history is an overwrite: the provider is correcting itself, and the
    # later answer is the one it stands behind.
    await write_candles(db, [candle(source=CandleSource.HISTORY, close=100.5)])
    await write_candles(db, [candle(source=CandleSource.HISTORY, close=123.0)])

    assert (await read_candles(db, "US100", Resolution.MINUTE))[0].close == 123.0


@pytest.mark.db
async def test_a_later_streamed_candle_replaces_an_earlier_one(db: asyncpg.Connection) -> None:
    # Stream over stream still overwrites. Only a stored *history* value is protected.
    await write_candles(db, [candle(source=CandleSource.STREAM, close=100.5)])
    await write_candles(db, [candle(source=CandleSource.STREAM, close=123.0)])

    assert (await read_candles(db, "US100", Resolution.MINUTE))[0].close == 123.0


@pytest.mark.db
async def test_a_declined_write_is_not_counted_as_written(db: asyncpg.Connection) -> None:
    # A caller reporting progress needs "written" to mean written.
    await write_candles(db, [candle(source=CandleSource.HISTORY)])

    assert await write_candles(db, [candle(source=CandleSource.STREAM)]) == 0


@pytest.mark.db
async def test_a_batch_reports_only_the_rows_the_archive_took(db: asyncpg.Connection) -> None:
    await write_candles(db, [candle(source=CandleSource.HISTORY)])

    written = await write_candles(
        db,
        [
            candle(source=CandleSource.STREAM),  # declined: history already holds it
            candle(period_start=MOMENT + timedelta(minutes=1), source=CandleSource.STREAM),
        ],
    )

    assert written == 1
    assert len(await read_candles(db, "US100", Resolution.MINUTE)) == 2


@pytest.mark.db
async def test_the_same_period_twice_in_one_batch_is_one_row(db: asyncpg.Connection) -> None:
    # Postgres refuses an ON CONFLICT that would touch a row twice in one statement, so
    # the batch is keyed before it is sent; the last offer for a period is the one meant.
    written = await write_candles(
        db, [candle(close=100.5), candle(close=123.0)]
    )

    assert written == 1
    assert (await read_candles(db, "US100", Resolution.MINUTE))[0].close == 123.0


@pytest.mark.db
async def test_the_same_period_at_another_resolution_is_another_candle(
    db: asyncpg.Connection,
) -> None:
    await write_candles(db, [candle(resolution=Resolution.MINUTE)])
    await write_candles(db, [candle(resolution=Resolution.HOUR)])

    assert len(await read_candles(db, "US100", Resolution.MINUTE)) == 1
    assert len(await read_candles(db, "US100", Resolution.HOUR)) == 1


@pytest.mark.db
async def test_a_range_read_comes_back_oldest_first(db: asyncpg.Connection) -> None:
    written = [candle(period_start=MOMENT + timedelta(minutes=m)) for m in (3, 0, 2, 1)]
    await write_candles(db, written)

    stored = await read_candles(db, "US100", Resolution.MINUTE)
    assert [c.period_start for c in stored] == [
        MOMENT + timedelta(minutes=m) for m in (0, 1, 2, 3)
    ]


@pytest.mark.db
async def test_a_range_read_excludes_its_end_so_two_reads_join_cleanly(
    db: asyncpg.Connection,
) -> None:
    await write_candles(
        db, [candle(period_start=MOMENT + timedelta(minutes=m)) for m in range(4)]
    )
    seam = MOMENT + timedelta(minutes=2)

    first = await read_candles(db, "US100", Resolution.MINUTE, MOMENT, seam)
    second = await read_candles(db, "US100", Resolution.MINUTE, seam)

    joined = [c.period_start for c in [*first, *second]]
    assert joined == sorted(set(joined))
    assert len(joined) == 4



@pytest.mark.db
async def test_a_forming_candle_is_refused(db: asyncpg.Connection) -> None:
    with pytest.raises(FormingCandleRejected):
        await write_candles(db, [candle(forming=True)])

    assert await read_candles(db, "US100", Resolution.MINUTE) == []


@pytest.mark.db
async def test_a_forming_candle_names_the_period_it_belongs_to(db: asyncpg.Connection) -> None:
    with pytest.raises(FormingCandleRejected) as err:
        await write_candles(db, [candle(forming=True)])
    assert "US100" in str(err.value)
    assert MOMENT.isoformat() in str(err.value)


@pytest.mark.db
async def test_one_forming_candle_rejects_the_whole_batch(db: asyncpg.Connection) -> None:
    # Half a batch written is worse than none: the caller has no way to learn which half
    # landed, and the gap surfaces weeks later when the provider no longer has the data.
    batch = [
        candle(period_start=MOMENT),
        candle(period_start=MOMENT + timedelta(minutes=1), forming=True),
    ]
    with pytest.raises(FormingCandleRejected):
        await write_candles(db, batch)

    assert await read_candles(db, "US100", Resolution.MINUTE) == []


@pytest.mark.db
async def test_a_closed_candle_replaces_nothing_a_forming_one_left_behind(
    db: asyncpg.Connection,
) -> None:
    # The forming candle never reached storage, so closing the period is an ordinary
    # first write rather than a correction.
    with pytest.raises(FormingCandleRejected):
        await write_candles(db, [candle(close=99.0, forming=True)])
    await write_candles(db, [candle(close=100.5)])

    stored = await read_candles(db, "US100", Resolution.MINUTE)
    assert [c.close for c in stored] == [100.5]


@pytest.mark.db
async def test_writing_nothing_is_allowed(db: asyncpg.Connection) -> None:
    assert await write_candles(db, []) == 0
