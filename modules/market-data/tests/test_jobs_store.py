"""jobs/store.py and the status derivation in jobs/models.py.

Group 2 of rework-instrument-collection: a job's status is never stored, only derived
from its chunks — so most of what is worth testing here is that the derivation reads
the same regardless of which write put the chunks in that shape.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import asyncpg
import pytest

from market_data.coverage import read_coverage, record_coverage
from market_data.jobs.models import ChunkPlan, ChunkState, JobStatus, derive_status
from market_data.jobs.store import (
    JobStillRunning,
    NothingToRetry,
    UnknownJob,
    claim_pending_chunk,
    create_job,
    delete_job,
    finish_chunk_done,
    finish_chunk_failed,
    finish_chunk_skipped,
    interrupt_orphaned_chunks,
    list_jobs,
    read_job,
    retry_job,
    skip_chunks_beyond_history,
)
from market_data.models import Candle, CandleSource, Resolution
from market_data.store import read_candles, write_candles
from market_data.tracking import track

MOMENT = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)
LIMIT = 20


def plan(symbol: str = "US100", resolution: Resolution = Resolution.MINUTE, **overrides) -> ChunkPlan:
    values = {
        "symbol": symbol,
        "resolution": resolution,
        "chunk_start": MOMENT - timedelta(days=1),
        "chunk_end": MOMENT,
        **overrides,
    }
    return ChunkPlan(**values)


def _candle(period_start: datetime, symbol: str = "US100") -> Candle:
    return Candle(
        symbol=symbol,
        resolution=Resolution.MINUTE,
        period_start=period_start,
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=10.0,
        source=CandleSource.HISTORY,
    )


async def _tracked(db: asyncpg.Connection, symbol: str = "US100", resolution: Resolution = Resolution.MINUTE):
    await track(db, symbol, resolution, LIMIT)


# --- status derivation (pure) --------------------------------------------------------


def test_a_job_with_no_chunks_succeeded_trivially() -> None:
    # Every pair in the decision was already fully covered — there was nothing to
    # fetch, and that is a success, not an empty question mark.
    assert derive_status([]) is JobStatus.SUCCEEDED


def test_any_open_chunk_means_the_job_is_running() -> None:
    assert derive_status([ChunkState.DONE, ChunkState.PENDING]) is JobStatus.RUNNING
    assert derive_status([ChunkState.RUNNING]) is JobStatus.RUNNING


def test_all_done_is_succeeded() -> None:
    assert derive_status([ChunkState.DONE, ChunkState.DONE, ChunkState.SKIPPED]) is JobStatus.SUCCEEDED


def test_a_mix_of_done_and_failed_is_partial() -> None:
    assert derive_status([ChunkState.DONE, ChunkState.FAILED]) is JobStatus.PARTIAL


def test_a_mix_of_done_and_interrupted_is_partial() -> None:
    assert derive_status([ChunkState.DONE, ChunkState.INTERRUPTED]) is JobStatus.PARTIAL


def test_all_failed_with_nothing_settled_is_failed() -> None:
    assert derive_status([ChunkState.FAILED, ChunkState.FAILED]) is JobStatus.FAILED


def test_all_interrupted_with_nothing_settled_is_interrupted() -> None:
    assert derive_status([ChunkState.INTERRUPTED, ChunkState.INTERRUPTED]) is JobStatus.INTERRUPTED


# --- creating and reading a job -------------------------------------------------------


@pytest.mark.db
async def test_a_job_with_no_plans_is_created_with_no_chunks(db: asyncpg.Connection) -> None:
    job = await create_job(db, MOMENT, [])
    assert job.chunks == []
    assert job.status is JobStatus.SUCCEEDED


@pytest.mark.db
async def test_a_job_carries_every_chunk_it_was_planned_with(db: asyncpg.Connection) -> None:
    await _tracked(db, "US100", Resolution.MINUTE)
    await _tracked(db, "US100", Resolution.HOUR)

    job = await create_job(
        db,
        MOMENT,
        [plan(resolution=Resolution.MINUTE), plan(resolution=Resolution.HOUR)],
    )

    assert len(job.chunks) == 2
    assert job.pairs == {("US100", Resolution.MINUTE), ("US100", Resolution.HOUR)}
    assert all(chunk.state is ChunkState.PENDING for chunk in job.chunks)


@pytest.mark.db
async def test_a_chunk_for_an_untracked_pair_is_refused(db: asyncpg.Connection) -> None:
    # The foreign key on (symbol, resolution) does the refusing; this proves the
    # boundary is honoured end to end through create_job, not only at the SQL layer.
    with pytest.raises(asyncpg.exceptions.ForeignKeyViolationError):
        await create_job(db, MOMENT, [plan()])


@pytest.mark.db
async def test_reading_an_unknown_job_is_none(db: asyncpg.Connection) -> None:
    assert await read_job(db, 999_999) is None


# --- claiming and finishing chunks -----------------------------------------------------


@pytest.mark.db
async def test_claiming_marks_a_chunk_running(db: asyncpg.Connection) -> None:
    await _tracked(db)
    await create_job(db, MOMENT, [plan()])

    claimed = await claim_pending_chunk(db)

    assert claimed is not None
    assert claimed.state is ChunkState.RUNNING
    assert claimed.started_at is not None


@pytest.mark.db
async def test_claiming_with_nothing_pending_is_none(db: asyncpg.Connection) -> None:
    assert await claim_pending_chunk(db) is None


@pytest.mark.db
async def test_claimed_chunks_are_not_claimed_twice(db: asyncpg.Connection) -> None:
    await _tracked(db)
    await create_job(db, MOMENT, [plan(), plan(chunk_start=MOMENT - timedelta(days=2), chunk_end=MOMENT - timedelta(days=1))])

    first = await claim_pending_chunk(db)
    second = await claim_pending_chunk(db)
    third = await claim_pending_chunk(db)

    assert first is not None and second is not None
    assert first.id != second.id
    assert third is None


@pytest.mark.db
async def test_a_done_chunk_carries_what_it_wrote(db: asyncpg.Connection) -> None:
    await _tracked(db)
    job = await create_job(db, MOMENT, [plan()])
    chunk = job.chunks[0]

    await claim_pending_chunk(db)
    await finish_chunk_done(db, chunk.id, written=120, requests=3)

    reread = await read_job(db, job.id)
    assert reread.status is JobStatus.SUCCEEDED
    assert reread.candles_written == 120
    assert reread.progress == (1, 1)


@pytest.mark.db
async def test_a_skipped_chunk_counts_as_settled_not_failed(db: asyncpg.Connection) -> None:
    await _tracked(db)
    job = await create_job(db, MOMENT, [plan()])
    chunk = job.chunks[0]

    await claim_pending_chunk(db)
    await finish_chunk_skipped(db, chunk.id, requests=1)

    reread = await read_job(db, job.id)
    assert reread.status is JobStatus.SUCCEEDED
    assert reread.progress == (1, 1)


@pytest.mark.db
async def test_a_failed_chunk_carries_its_reason(db: asyncpg.Connection) -> None:
    await _tracked(db)
    job = await create_job(db, MOMENT, [plan()])
    chunk = job.chunks[0]

    await claim_pending_chunk(db)
    await finish_chunk_failed(db, chunk.id, failure="the gateway refused with 502", requests=1)

    reread = await read_job(db, job.id)
    assert reread.status is JobStatus.FAILED
    assert reread.chunks[0].failure == "the gateway refused with 502"


@pytest.mark.db
async def test_a_partial_job_names_the_pair_still_running(db: asyncpg.Connection) -> None:
    await _tracked(db, "US100", Resolution.MINUTE)
    await _tracked(db, "US100", Resolution.HOUR)
    job = await create_job(
        db, MOMENT, [plan(resolution=Resolution.MINUTE), plan(resolution=Resolution.HOUR)]
    )

    running = await claim_pending_chunk(db)

    reread = await read_job(db, job.id)
    assert reread.running_pair == (running.symbol, running.resolution)


# --- restart: orphaned chunks ---------------------------------------------------------


@pytest.mark.db
async def test_startup_interrupts_a_running_chunk(db: asyncpg.Connection) -> None:
    await _tracked(db)
    job = await create_job(db, MOMENT, [plan()])
    await claim_pending_chunk(db)

    count = await interrupt_orphaned_chunks(db)

    assert count == 1
    reread = await read_job(db, job.id)
    assert reread.chunks[0].state is ChunkState.INTERRUPTED
    assert reread.status is JobStatus.INTERRUPTED


@pytest.mark.db
async def test_startup_interrupts_chunks_still_queued(db: asyncpg.Connection) -> None:
    """A chunk that never got as far as running is exactly as orphaned as one that did
    — no runner survived to work either of them (design.md, "Historia zleceń i
    kawałków przeżywa restart")."""
    await _tracked(db)
    job = await create_job(db, MOMENT, [plan()])
    # Left pending, deliberately not claimed — the runner that would have picked it up
    # died with the process, same as the one that had already claimed a different chunk.

    await interrupt_orphaned_chunks(db)

    reread = await read_job(db, job.id)
    assert reread.chunks[0].state is ChunkState.INTERRUPTED
    assert reread.status is JobStatus.INTERRUPTED


@pytest.mark.db
async def test_settled_chunks_are_untouched_by_a_restart(db: asyncpg.Connection) -> None:
    await _tracked(db)
    job = await create_job(db, MOMENT, [plan()])
    await claim_pending_chunk(db)
    await finish_chunk_done(db, job.chunks[0].id, written=10, requests=1)

    await interrupt_orphaned_chunks(db)

    reread = await read_job(db, job.id)
    assert reread.chunks[0].state is ChunkState.DONE


# --- retrying ---------------------------------------------------------------------------


@pytest.mark.db
async def test_retrying_resets_only_failed_and_interrupted_chunks(db: asyncpg.Connection) -> None:
    await _tracked(db, "US100", Resolution.MINUTE)
    await _tracked(db, "US100", Resolution.HOUR)
    job = await create_job(
        db, MOMENT, [plan(resolution=Resolution.MINUTE), plan(resolution=Resolution.HOUR)]
    )
    done_chunk, other_chunk = job.chunks
    await claim_pending_chunk(db)
    await finish_chunk_done(db, done_chunk.id, written=5, requests=1)
    await claim_pending_chunk(db)
    await finish_chunk_failed(db, other_chunk.id, failure="boom", requests=1)

    retried = await retry_job(db, job.id)

    by_id = {chunk.id: chunk for chunk in retried.chunks}
    assert by_id[done_chunk.id].state is ChunkState.DONE
    assert by_id[other_chunk.id].state is ChunkState.PENDING
    assert by_id[other_chunk.id].failure is None
    assert retried.attempt == 2


@pytest.mark.db
async def test_retrying_bumps_the_reset_chunks_attempt(db: asyncpg.Connection) -> None:
    await _tracked(db)
    job = await create_job(db, MOMENT, [plan()])
    await claim_pending_chunk(db)
    await finish_chunk_failed(db, job.chunks[0].id, failure="boom", requests=1)

    retried = await retry_job(db, job.id)

    assert retried.chunks[0].attempt == 2


@pytest.mark.db
async def test_retrying_a_job_with_nothing_failed_is_refused(db: asyncpg.Connection) -> None:
    await _tracked(db)
    job = await create_job(db, MOMENT, [plan()])
    await claim_pending_chunk(db)
    await finish_chunk_done(db, job.chunks[0].id, written=5, requests=1)

    with pytest.raises(NothingToRetry):
        await retry_job(db, job.id)


@pytest.mark.db
async def test_retrying_an_unknown_job_is_refused(db: asyncpg.Connection) -> None:
    with pytest.raises(UnknownJob):
        await retry_job(db, 999_999)


# --- bulk-skipping chunks past a discovered boundary -----------------------------------


@pytest.mark.db
async def test_skipping_only_touches_pending_chunks_at_or_before_the_boundary(
    db: asyncpg.Connection,
) -> None:
    await _tracked(db)
    newest = plan(chunk_start=MOMENT - timedelta(days=1), chunk_end=MOMENT)
    boundary_chunk = plan(
        chunk_start=MOMENT - timedelta(days=2), chunk_end=MOMENT - timedelta(days=1)
    )
    older = plan(chunk_start=MOMENT - timedelta(days=3), chunk_end=MOMENT - timedelta(days=2))
    job = await create_job(db, MOMENT, [newest, boundary_chunk, older])

    # The boundary sits at the start of `boundary_chunk` — everything at or before it
    # (here, only `older`) is skipped; `newest` and `boundary_chunk` itself are not.
    skipped = await skip_chunks_beyond_history(
        db, job.id, "US100", Resolution.MINUTE, boundary_chunk.chunk_start
    )

    assert skipped == 1
    reread = await read_job(db, job.id)
    by_window = {(c.chunk_start, c.chunk_end): c.state for c in reread.chunks}
    assert by_window[(older.chunk_start, older.chunk_end)] is ChunkState.SKIPPED
    assert by_window[(boundary_chunk.chunk_start, boundary_chunk.chunk_end)] is ChunkState.PENDING
    assert by_window[(newest.chunk_start, newest.chunk_end)] is ChunkState.PENDING


@pytest.mark.db
async def test_skipping_does_not_touch_a_chunk_already_running(db: asyncpg.Connection) -> None:
    await _tracked(db)
    running = plan(chunk_start=MOMENT - timedelta(days=2), chunk_end=MOMENT - timedelta(days=1))
    job = await create_job(db, MOMENT, [running])
    claimed = await claim_pending_chunk(db)

    skipped = await skip_chunks_beyond_history(db, job.id, "US100", Resolution.MINUTE, MOMENT)

    assert skipped == 0
    reread = await read_job(db, job.id)
    assert reread.chunks[0].id == claimed.id
    assert reread.chunks[0].state is ChunkState.RUNNING


# --- listing, narrowed to a pair -------------------------------------------------------


@pytest.mark.db
async def test_listing_narrows_a_job_to_one_row_per_pair(db: asyncpg.Connection) -> None:
    await _tracked(db, "US100", Resolution.MINUTE)
    await _tracked(db, "US100", Resolution.HOUR)
    await create_job(
        db, MOMENT, [plan(resolution=Resolution.MINUTE), plan(resolution=Resolution.HOUR)]
    )

    views = await list_jobs(db)

    assert len(views) == 2
    assert {(v.symbol, v.resolution) for v in views} == {
        ("US100", Resolution.MINUTE),
        ("US100", Resolution.HOUR),
    }
    for view in views:
        assert len(view.chunks) == 1


@pytest.mark.db
async def test_listing_filtered_by_pair_excludes_other_pairs(db: asyncpg.Connection) -> None:
    await _tracked(db, "US100", Resolution.MINUTE)
    await _tracked(db, "US100", Resolution.HOUR)
    await create_job(
        db, MOMENT, [plan(resolution=Resolution.MINUTE), plan(resolution=Resolution.HOUR)]
    )

    views = await list_jobs(db, symbol="US100", resolution=Resolution.MINUTE)

    assert len(views) == 1
    assert views[0].resolution is Resolution.MINUTE


@pytest.mark.db
async def test_listing_orders_newest_job_first(db: asyncpg.Connection) -> None:
    await _tracked(db)
    first = await create_job(db, MOMENT - timedelta(days=1), [plan()])
    await claim_pending_chunk(db)
    await finish_chunk_done(db, first.chunks[0].id, written=1, requests=1)
    second = await create_job(db, MOMENT, [plan()])

    views = await list_jobs(db, symbol="US100", resolution=Resolution.MINUTE)

    assert [v.job_id for v in views] == [second.id, first.id]


@pytest.mark.db
async def test_a_job_spanning_two_pairs_reads_whole_through_read_job(
    db: asyncpg.Connection,
) -> None:
    await _tracked(db, "US100", Resolution.MINUTE)
    await _tracked(db, "US100", Resolution.HOUR)
    created = await create_job(
        db, MOMENT, [plan(resolution=Resolution.MINUTE), plan(resolution=Resolution.HOUR)]
    )

    whole = await read_job(db, created.id)

    assert len(whole.chunks) == 2


# --- when something last happened ------------------------------------------------------


@pytest.mark.db
async def test_a_running_chunk_is_the_jobs_last_activity(db: asyncpg.Connection) -> None:
    """The forty-minute evening in one assertion: a job whose only sign of life is a
    chunk that started is dated from that start, not from the chunk before it."""
    await _tracked(db)
    job = await create_job(db, MOMENT, [plan(), plan(chunk_start=MOMENT - timedelta(days=2))])

    first = await claim_pending_chunk(db)
    await finish_chunk_done(db, first.id, written=10, requests=1)
    running = await claim_pending_chunk(db)

    reread = await read_job(db, job.id)
    settled = next(c for c in reread.chunks if c.id == first.id)
    started = next(c for c in reread.chunks if c.id == running.id)

    assert reread.last_activity_at == started.started_at
    assert reread.last_activity_at > settled.finished_at


@pytest.mark.db
async def test_a_job_with_nothing_started_yet_dates_from_its_creation(
    db: asyncpg.Connection,
) -> None:
    # "Since when has nothing happened" has to have an answer even before the first
    # chunk is claimed, or a job queued behind a stuck one reads as having no age.
    await _tracked(db)
    job = await create_job(db, MOMENT, [plan()])

    reread = await read_job(db, job.id)

    assert reread.last_activity_at == job.created_at


@pytest.mark.db
async def test_a_pair_row_counts_only_its_own_pairs_activity(db: asyncpg.Connection) -> None:
    await _tracked(db, "US100", Resolution.MINUTE)
    await _tracked(db, "US100", Resolution.HOUR)
    job = await create_job(
        db, MOMENT, [plan(resolution=Resolution.MINUTE), plan(resolution=Resolution.HOUR)]
    )

    # Only the minute pair does any work; the hour pair sits untouched.
    working = await claim_pending_chunk(db)
    await finish_chunk_done(db, working.id, written=5, requests=1)

    views = {v.resolution: v for v in await list_jobs(db)}

    assert views[Resolution.MINUTE].last_activity_at > job.created_at
    assert views[Resolution.HOUR].last_activity_at == job.created_at


@pytest.mark.db
async def test_a_stalled_job_reports_the_same_moment_on_every_read(
    db: asyncpg.Connection,
) -> None:
    # The tab re-reads every ten seconds. A moment that crept forward with each read
    # would make a stuck job look busy — which is the failure this exists to catch.
    await _tracked(db)
    job = await create_job(db, MOMENT, [plan()])
    await claim_pending_chunk(db)

    first = (await read_job(db, job.id)).last_activity_at
    second = (await read_job(db, job.id)).last_activity_at

    assert first == second


# --- removing a job from the history ---------------------------------------------------


@pytest.mark.db
async def test_deleting_a_settled_job_takes_its_chunks_with_it(db: asyncpg.Connection) -> None:
    await _tracked(db)
    job = await create_job(db, MOMENT, [plan()])
    claimed = await claim_pending_chunk(db)
    await finish_chunk_done(db, claimed.id, written=120, requests=3)

    await delete_job(db, job.id)

    assert await read_job(db, job.id) is None
    left = await db.fetchval(
        "SELECT count(*) FROM collection_job_chunks WHERE job_id = $1", job.id
    )
    assert left == 0


@pytest.mark.db
async def test_deleting_a_job_with_a_pending_chunk_is_refused(db: asyncpg.Connection) -> None:
    # `pending` is refused for the same reason `running` is: the runner claims it a
    # moment later and writes its result against a job that would no longer exist.
    await _tracked(db)
    job = await create_job(db, MOMENT, [plan()])

    with pytest.raises(JobStillRunning):
        await delete_job(db, job.id)

    reread = await read_job(db, job.id)
    assert reread is not None
    assert len(reread.chunks) == 1


@pytest.mark.db
async def test_deleting_a_job_with_a_running_chunk_is_refused(db: asyncpg.Connection) -> None:
    await _tracked(db)
    job = await create_job(db, MOMENT, [plan()])
    await claim_pending_chunk(db)

    with pytest.raises(JobStillRunning):
        await delete_job(db, job.id)

    assert (await read_job(db, job.id)) is not None


@pytest.mark.db
async def test_deleting_a_failed_job_is_allowed(db: asyncpg.Connection) -> None:
    # Nothing is open, so nothing can be racing — a job worth removing is usually one
    # that went wrong.
    await _tracked(db)
    job = await create_job(db, MOMENT, [plan()])
    claimed = await claim_pending_chunk(db)
    await finish_chunk_failed(db, claimed.id, failure="the gateway refused with 502", requests=1)

    await delete_job(db, job.id)

    assert await read_job(db, job.id) is None


@pytest.mark.db
async def test_deleting_an_unknown_job_is_refused_and_removes_nothing(
    db: asyncpg.Connection,
) -> None:
    await _tracked(db)
    job = await create_job(db, MOMENT, [plan()])

    with pytest.raises(UnknownJob):
        await delete_job(db, 999_999)

    assert await read_job(db, job.id) is not None


@pytest.mark.db
async def test_deleting_one_job_leaves_the_pairs_other_jobs_alone(
    db: asyncpg.Connection,
) -> None:
    await _tracked(db)
    first = await create_job(db, MOMENT - timedelta(days=1), [plan()])
    claimed = await claim_pending_chunk(db)
    await finish_chunk_done(db, claimed.id, written=40, requests=1)
    second = await create_job(db, MOMENT, [plan()])
    running = await claim_pending_chunk(db)
    await finish_chunk_failed(db, running.id, failure="nope", requests=1)

    await delete_job(db, second.id)

    kept = await read_job(db, first.id)
    assert kept is not None
    assert kept.status is JobStatus.SUCCEEDED
    assert kept.candles_written == 40
    assert [v.job_id for v in await list_jobs(db)] == [first.id]


@pytest.mark.db
async def test_deleting_a_job_leaves_its_candles_and_coverage_untouched(
    db: asyncpg.Connection,
) -> None:
    """The whole point of the operation, in one assertion: history says what was done,
    it does not hold the data, and removing the record MUST NOT undo the work."""
    await _tracked(db)
    job = await create_job(db, MOMENT, [plan()])
    claimed = await claim_pending_chunk(db)
    await write_candles(db, [_candle(MOMENT - timedelta(minutes=n)) for n in range(3)])
    await record_coverage(db, "US100", Resolution.MINUTE, MOMENT - timedelta(days=1), MOMENT)
    await finish_chunk_done(db, claimed.id, written=3, requests=1)

    await delete_job(db, job.id)

    # Half-open, like every range in this module — hence the minute past `MOMENT`.
    kept = await read_candles(
        db, "US100", Resolution.MINUTE, MOMENT - timedelta(days=1), MOMENT + timedelta(minutes=1)
    )
    assert len(kept) == 3
    ranges = await read_coverage(db, "US100", Resolution.MINUTE)
    assert [(r.range_start, r.range_end) for r in ranges] == [(MOMENT - timedelta(days=1), MOMENT)]
