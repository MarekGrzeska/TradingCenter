"""deletion.py — kasowanie a pair's data, and the trace it leaves behind. Everything the pair touched
except the live ingest task, which the endpoint stops between the two calls."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import asyncpg
import pytest

from market_data.coverage import Absence, absence_at, read_coverage, record_coverage
from market_data.deletion import close_for_deletion, delete_pair_data, read_deletions
from market_data.jobs.models import ChunkPlan, ChunkState
from market_data.jobs.store import claim_pending_chunk, create_job, read_job
from market_data.models import Candle, CandleSource, Resolution
from market_data.rollups import read_derived, refresh_all
from market_data.store import read_candles, write_candles
from market_data.tracking import is_tracked, track

pytestmark = pytest.mark.db

MOMENT = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)
LIMIT = 20


def candle(symbol: str = "US100", resolution: Resolution = Resolution.MINUTE, **overrides):
    return Candle(
        **{
            "symbol": symbol,
            "resolution": resolution,
            "period_start": MOMENT,
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 10.0,
            "source": CandleSource.HISTORY,
            **overrides,
        }
    )


def plan(
    symbol: str = "US100", resolution: Resolution = Resolution.MINUTE, **overrides
) -> ChunkPlan:
    values = {
        "symbol": symbol,
        "resolution": resolution,
        "chunk_start": MOMENT - timedelta(days=1),
        "chunk_end": MOMENT,
        **overrides,
    }
    return ChunkPlan(**values)



async def test_deleting_a_pair_with_candles_records_the_count_and_range(
    db: asyncpg.Connection,
) -> None:
    await track(db, "US100", Resolution.MINUTE, LIMIT)
    await write_candles(db, [candle(period_start=MOMENT - timedelta(minutes=m)) for m in range(3)])

    await close_for_deletion(db, "US100", Resolution.MINUTE)
    deletion = await delete_pair_data(db, "US100", Resolution.MINUTE)

    assert deletion.candles_removed == 3
    assert deletion.removed_from == MOMENT - timedelta(minutes=2)
    assert deletion.removed_to == MOMENT


async def test_deleting_a_pair_with_nothing_collected_records_zero(
    db: asyncpg.Connection,
) -> None:
    await track(db, "US100", Resolution.MINUTE, LIMIT)

    await close_for_deletion(db, "US100", Resolution.MINUTE)
    deletion = await delete_pair_data(db, "US100", Resolution.MINUTE)

    assert deletion.candles_removed == 0
    assert deletion.removed_from is None
    assert deletion.removed_to is None


async def test_reading_deletions_is_narrowed_to_one_pair(db: asyncpg.Connection) -> None:
    await track(db, "US100", Resolution.MINUTE, LIMIT)
    await track(db, "GOLD", Resolution.HOUR, LIMIT)
    await close_for_deletion(db, "US100", Resolution.MINUTE)
    await delete_pair_data(db, "US100", Resolution.MINUTE)
    await close_for_deletion(db, "GOLD", Resolution.HOUR)
    await delete_pair_data(db, "GOLD", Resolution.HOUR)

    deletions = await read_deletions(db, symbol="US100", resolution=Resolution.MINUTE)

    assert [d.symbol for d in deletions] == ["US100"]


async def test_a_deletion_survives_a_fresh_connection(migrated_url: str) -> None:
    from market_data.db import asyncpg_dsn

    conn = await asyncpg.connect(asyncpg_dsn(migrated_url))
    try:
        await conn.execute(
            "TRUNCATE candles, derived_candles, tracked_pairs, coverage_ranges, "
            "collection_jobs, collection_job_chunks, pair_deletions"
        )
        await track(conn, "US100", Resolution.MINUTE, LIMIT)
        await close_for_deletion(conn, "US100", Resolution.MINUTE)
        await delete_pair_data(conn, "US100", Resolution.MINUTE)
    finally:
        await conn.close()

    other = await asyncpg.connect(asyncpg_dsn(migrated_url))
    try:
        deletions = await read_deletions(other)
    finally:
        await other.close()

    assert [d.symbol for d in deletions] == ["US100"]



async def test_deleting_removes_candles_and_coverage(db: asyncpg.Connection) -> None:
    await track(db, "US100", Resolution.MINUTE, LIMIT)
    await write_candles(db, [candle()])
    await record_coverage(db, "US100", Resolution.MINUTE, MOMENT - timedelta(hours=1), MOMENT)

    await close_for_deletion(db, "US100", Resolution.MINUTE)
    await delete_pair_data(db, "US100", Resolution.MINUTE)

    assert await read_candles(db, "US100", Resolution.MINUTE) == []
    assert await read_coverage(db, "US100", Resolution.MINUTE) == []


async def test_deleting_the_minute_series_removes_its_rollups(db: asyncpg.Connection) -> None:
    await track(db, "US100", Resolution.MINUTE, LIMIT)
    await write_candles(db, [candle(period_start=MOMENT - timedelta(minutes=m)) for m in range(10)])
    await refresh_all(db, "US100", MOMENT - timedelta(minutes=10), MOMENT)
    assert await read_derived(db, "US100", Resolution.MINUTE_5) != []

    await close_for_deletion(db, "US100", Resolution.MINUTE)
    await delete_pair_data(db, "US100", Resolution.MINUTE)

    assert await read_derived(db, "US100", Resolution.MINUTE_5) == []


async def test_deleting_one_resolution_leaves_another_archived_one_of_the_same_symbol_alone(
    db: asyncpg.Connection,
) -> None:
    await track(db, "US100", Resolution.MINUTE, LIMIT)
    await track(db, "US100", Resolution.HOUR, LIMIT)
    await write_candles(
        db, [candle(resolution=Resolution.MINUTE), candle(resolution=Resolution.HOUR)]
    )
    await record_coverage(db, "US100", Resolution.HOUR, MOMENT - timedelta(hours=1), MOMENT)

    await close_for_deletion(db, "US100", Resolution.MINUTE)
    await delete_pair_data(db, "US100", Resolution.MINUTE)

    assert len(await read_candles(db, "US100", Resolution.HOUR)) == 1
    assert len(await read_coverage(db, "US100", Resolution.HOUR)) == 1


async def test_a_period_that_was_covered_before_deletion_reads_as_not_collected(
    db: asyncpg.Connection,
) -> None:
    await track(db, "US100", Resolution.MINUTE, LIMIT)
    await record_coverage(db, "US100", Resolution.MINUTE, MOMENT - timedelta(hours=1), MOMENT)
    assert await absence_at(db, "US100", Resolution.MINUTE, MOMENT - timedelta(minutes=30)) is (
        Absence.MARKET_CLOSED
    )

    await close_for_deletion(db, "US100", Resolution.MINUTE)
    await delete_pair_data(db, "US100", Resolution.MINUTE)

    assert (
        await absence_at(db, "US100", Resolution.MINUTE, MOMENT - timedelta(minutes=30))
        is Absence.NOT_COLLECTED
    )



async def test_closing_for_deletion_untracks_the_pair(db: asyncpg.Connection) -> None:
    await track(db, "US100", Resolution.MINUTE, LIMIT)

    stopped = await close_for_deletion(db, "US100", Resolution.MINUTE)

    assert stopped is not None
    assert await is_tracked(db, "US100", Resolution.MINUTE) is False


async def test_closing_for_deletion_on_a_pair_never_tracked_is_none(
    db: asyncpg.Connection,
) -> None:
    assert await close_for_deletion(db, "US100", Resolution.MINUTE) is None


async def test_closing_for_deletion_skips_pending_chunks_of_the_pair(
    db: asyncpg.Connection,
) -> None:
    await track(db, "US100", Resolution.MINUTE, LIMIT)
    job = await create_job(db, MOMENT, [plan()])

    await close_for_deletion(db, "US100", Resolution.MINUTE)

    reread = await read_job(db, job.id)
    assert [c.state for c in reread.chunks] == [ChunkState.SKIPPED]


async def test_closing_for_deletion_does_not_touch_a_chunk_already_running(
    db: asyncpg.Connection,
) -> None:
    await track(db, "US100", Resolution.MINUTE, LIMIT)
    job = await create_job(db, MOMENT, [plan()])
    claimed = await claim_pending_chunk(db)
    assert claimed is not None

    await close_for_deletion(db, "US100", Resolution.MINUTE)

    reread = await read_job(db, job.id)
    assert [c.state for c in reread.chunks] == [ChunkState.RUNNING]



async def test_a_pair_re_added_after_deletion_has_no_leftover_coverage(
    db: asyncpg.Connection,
) -> None:
    await track(db, "US100", Resolution.MINUTE, LIMIT)
    await write_candles(db, [candle()])
    await record_coverage(db, "US100", Resolution.MINUTE, MOMENT - timedelta(days=365), MOMENT)

    await close_for_deletion(db, "US100", Resolution.MINUTE)
    await delete_pair_data(db, "US100", Resolution.MINUTE)
    await track(db, "US100", Resolution.MINUTE, LIMIT, collect_from=MOMENT - timedelta(days=365))

    assert await read_coverage(db, "US100", Resolution.MINUTE) == []
    assert (
        await absence_at(db, "US100", Resolution.MINUTE, MOMENT - timedelta(days=100))
        is Absence.NOT_COLLECTED
    )
