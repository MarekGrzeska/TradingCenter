"""jobs/plan.py: turning a request into chunks, and pricing it without running it.

Group 3 of rework-instrument-collection.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import asyncpg
import pytest

from market_data.coverage import earliest_reachable, record_coverage
from market_data.jobs.plan import (
    ESTIMATED_BYTES_PER_CANDLE,
    FutureRequest,
    estimate_job,
    plan_chunks,
    split_into_windows,
)
from market_data.models import Resolution
from market_data.periods import periods_between
from market_data.tracking import track

MOMENT = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)
LIMIT = 20


async def _tracked(db: asyncpg.Connection, symbol: str = "US100", resolution: Resolution = Resolution.MINUTE):
    await track(db, symbol, resolution, LIMIT, collect_from=MOMENT - timedelta(days=3650))


# --- pure arithmetic -------------------------------------------------------------------


def test_a_window_narrower_than_the_ceiling_is_one_chunk() -> None:
    windows = split_into_windows(Resolution.DAY, MOMENT - timedelta(days=10), MOMENT)
    assert len(windows) == 1
    assert windows[0] == (MOMENT - timedelta(days=10), MOMENT)


def test_a_wide_gap_splits_at_the_bars_ceiling() -> None:
    # MINUTE at 50_000 bars is a touch under 35 days; a 40-day gap needs two chunks.
    start = MOMENT - timedelta(days=40)
    windows = split_into_windows(Resolution.MINUTE, start, MOMENT)
    assert len(windows) == 2
    # Newest window first — the one ending at `MOMENT` runs before the one reaching
    # further back, so a chunk that discovers the provider's boundary runs early.
    assert windows[0][1] == MOMENT
    assert windows[-1][0] == start
    # Contiguous: the older window ends exactly where the newer one starts.
    assert windows[1][1] == windows[0][0]


def test_windows_never_exceed_the_bars_ceiling() -> None:
    start = MOMENT - timedelta(days=365 * 5)
    for window_start, window_end in split_into_windows(Resolution.MINUTE, start, MOMENT):
        assert periods_between(Resolution.MINUTE, window_start, window_end) <= 50_000


def test_an_empty_gap_produces_no_windows() -> None:
    assert split_into_windows(Resolution.MINUTE, MOMENT, MOMENT) == []


def test_windows_run_newest_to_oldest() -> None:
    start = MOMENT - timedelta(days=200)
    windows = split_into_windows(Resolution.MINUTE, start, MOMENT)
    assert len(windows) > 2
    ends = [window_end for _, window_end in windows]
    assert ends == sorted(ends, reverse=True)


# --- planning against the archive -------------------------------------------------------


@pytest.mark.db
async def test_a_future_request_is_refused(db: asyncpg.Connection) -> None:
    await _tracked(db)
    with pytest.raises(FutureRequest):
        await plan_chunks(db, "US100", Resolution.MINUTE, MOMENT + timedelta(days=1), MOMENT)


@pytest.mark.db
async def test_a_pair_with_nothing_covered_plans_one_gap(db: asyncpg.Connection) -> None:
    await _tracked(db)
    requested_from = MOMENT - timedelta(days=5)

    chunks, effective_from = await plan_chunks(db, "US100", Resolution.MINUTE, requested_from, MOMENT)

    assert effective_from == requested_from
    assert len(chunks) == 1
    assert chunks[0].chunk_start == requested_from
    assert chunks[0].chunk_end == MOMENT


@pytest.mark.db
async def test_a_fully_covered_pair_plans_nothing(db: asyncpg.Connection) -> None:
    await _tracked(db)
    requested_from = MOMENT - timedelta(days=5)
    await record_coverage(db, "US100", Resolution.MINUTE, requested_from, MOMENT)

    chunks, _ = await plan_chunks(db, "US100", Resolution.MINUTE, requested_from, MOMENT)

    assert chunks == []


@pytest.mark.db
async def test_a_partly_covered_pair_plans_only_the_gap(db: asyncpg.Connection) -> None:
    await _tracked(db)
    requested_from = MOMENT - timedelta(days=5)
    # The newest half is already collected; only the older half is missing.
    await record_coverage(db, "US100", Resolution.MINUTE, MOMENT - timedelta(days=2), MOMENT)

    chunks, _ = await plan_chunks(db, "US100", Resolution.MINUTE, requested_from, MOMENT)

    assert len(chunks) == 1
    assert chunks[0].chunk_start == requested_from
    assert chunks[0].chunk_end == MOMENT - timedelta(days=2)


@pytest.mark.db
async def test_a_recorded_boundary_does_not_clip_a_deeper_request(
    db: asyncpg.Connection,
) -> None:
    """The defect, in the place it was silent.

    A boundary recorded once raised every later request up to it, so a pair whose boundary
    was wrong — or merely stale, since the provider deepens its own history — could not be
    deepened by any request at all. US100 asked for 2024 against a boundary at 2026 planned
    no chunks and reported itself done with zero candles.

    Planning no longer reads the boundary. Dropping it is the job-creating path's business
    (`routers/pairs.py`), which is what keeps pricing free of writes.
    """
    await _tracked(db)
    boundary = MOMENT - timedelta(days=30)
    await record_coverage(
        db,
        "US100",
        Resolution.MINUTE,
        boundary,
        MOMENT - timedelta(days=29),
        history_ended=True,
        history_ends_at=boundary,
    )

    requested_from = MOMENT - timedelta(days=60)
    chunks, effective_from = await plan_chunks(db, "US100", Resolution.MINUTE, requested_from, MOMENT)

    assert effective_from == requested_from
    assert chunks, "a deeper request must plan the work that measures the boundary again"
    assert min(chunk.chunk_start for chunk in chunks) == requested_from


# --- estimating --------------------------------------------------------------------------


@pytest.mark.db
async def test_an_estimate_prices_every_pair_and_sums_them(db: asyncpg.Connection) -> None:
    await _tracked(db, "US100", Resolution.MINUTE)
    await _tracked(db, "US100", Resolution.HOUR)
    requested_from = MOMENT - timedelta(days=5)

    result = await estimate_job(
        db, [("US100", Resolution.MINUTE), ("US100", Resolution.HOUR)], requested_from, MOMENT
    )

    assert len(result.pairs) == 2
    assert result.total_estimated_candles == sum(p.estimated_candles for p in result.pairs)
    assert result.total_estimated_bytes == result.total_estimated_candles * ESTIMATED_BYTES_PER_CANDLE


@pytest.mark.db
async def test_estimating_has_no_side_effects(db: asyncpg.Connection) -> None:
    await _tracked(db)
    requested_from = MOMENT - timedelta(days=5)

    await estimate_job(db, [("US100", Resolution.MINUTE)], requested_from, MOMENT)

    chunks, _ = await plan_chunks(db, "US100", Resolution.MINUTE, requested_from, MOMENT)
    # Still exactly what an un-estimated pair would plan — nothing was recorded as
    # covered, and no job was created, by pricing it.
    assert len(chunks) == 1
    assert chunks[0].chunk_start == requested_from


@pytest.mark.db
async def test_an_estimate_prices_what_the_job_will_do_and_writes_nothing(
    db: asyncpg.Connection,
) -> None:
    """The equality that makes a dialog worth showing: pricing and running compute the
    same range. Pricing gets there by not reading the boundary rather than by dropping it,
    which is what keeps it free of writes."""
    await _tracked(db)
    boundary = MOMENT - timedelta(days=10)
    await record_coverage(
        db,
        "US100",
        Resolution.MINUTE,
        boundary,
        MOMENT - timedelta(days=9),
        history_ended=True,
        history_ends_at=boundary,
    )
    requested_from = MOMENT - timedelta(days=40)

    result = await estimate_job(db, [("US100", Resolution.MINUTE)], requested_from, MOMENT)
    chunks, _ = await plan_chunks(db, "US100", Resolution.MINUTE, requested_from, MOMENT)

    assert result.pairs[0].effective_from == requested_from
    assert result.pairs[0].chunk_count == len(chunks)
    # And the boundary is exactly where it was: an estimate is a question, not an order.
    assert await earliest_reachable(db, "US100", Resolution.MINUTE) == boundary


@pytest.mark.db
async def test_an_unclipped_pair_says_so_too(db: asyncpg.Connection) -> None:
    await _tracked(db)
    requested_from = MOMENT - timedelta(days=5)

    result = await estimate_job(db, [("US100", Resolution.MINUTE)], requested_from, MOMENT)

    assert result.pairs[0].clipped is False
