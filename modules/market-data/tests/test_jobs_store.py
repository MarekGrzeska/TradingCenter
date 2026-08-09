"""jobs/store.py and the status derivation in jobs/models.py.

Group 2 of rework-instrument-collection: a job's status is never stored, only derived
from its chunks — so most of what is worth testing here is that the derivation reads
the same regardless of which write put the chunks in that shape.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import asyncpg
import pytest

from market_data.jobs.models import ChunkPlan, ChunkState, JobStatus, derive_status
from market_data.jobs.store import (
    NothingToRetry,
    UnknownJob,
    claim_pending_chunk,
    create_job,
    finish_chunk_done,
    finish_chunk_failed,
    finish_chunk_skipped,
    interrupt_orphaned_chunks,
    list_jobs,
    read_job,
    retry_job,
    skip_chunks_beyond_history,
)
from market_data.models import Resolution
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
