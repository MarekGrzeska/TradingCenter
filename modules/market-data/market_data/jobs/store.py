"""The only door to `collection_jobs` and `collection_job_chunks`.

Nothing here decides what a chunk's window should be — that is `plan.py` — or runs a
fetch — that is `runner.py`. This module only ever moves a job or a chunk between the
states `models.py` defines, and reads them back.
"""

from __future__ import annotations

from datetime import datetime

import asyncpg

from ..db import fetch_one
from ..models import Resolution
from .models import (
    OPEN_CHUNK_STATES,
    RETRYABLE_CHUNK_STATES,
    Chunk,
    ChunkPlan,
    ChunkState,
    Job,
    JobPairView,
    narrow_to_pairs,
)


class NothingToRetry(Exception):
    """A retry was asked of a job with no failed or interrupted chunk."""


class UnknownJob(Exception):
    """A job id nobody has ever created."""


class JobStillRunning(Exception):
    """A delete was asked of a job a runner may still take work from."""


_INSERT_JOB = """
    INSERT INTO collection_jobs (requested_from)
    VALUES ($1)
    RETURNING id, created_at, requested_from, attempt
"""

_INSERT_CHUNK = """
    INSERT INTO collection_job_chunks (job_id, symbol, resolution, chunk_start, chunk_end)
    VALUES ($1, $2, $3, $4, $5)
"""

_SELECT_JOB = """
    SELECT id, created_at, requested_from, attempt
      FROM collection_jobs
     WHERE id = $1
"""

_SELECT_CHUNKS_FOR_JOB = """
    SELECT id, job_id, symbol, resolution, chunk_start, chunk_end, state, attempt,
           candles_written, requests, failure, started_at, finished_at
      FROM collection_job_chunks
     WHERE job_id = $1
     ORDER BY id
"""

# Every job that has at least one chunk on the requested pair — or every job there is,
# when neither filter is given. Newest job first, matching how an operator reads a list:
# the thing that just happened belongs at the top.
_SELECT_MATCHING_JOB_IDS = """
    SELECT DISTINCT j.id, j.created_at
      FROM collection_jobs j
      JOIN collection_job_chunks c ON c.job_id = j.id
     WHERE ($1::text IS NULL OR c.symbol = $1)
       AND ($2::text IS NULL OR c.resolution = $2)
     ORDER BY j.created_at DESC
"""

_CLAIM_PENDING_CHUNK = """
    UPDATE collection_job_chunks
       SET state = 'running', started_at = now()
     WHERE id = (
         SELECT id
           FROM collection_job_chunks
          WHERE state = 'pending'
          ORDER BY job_id, id
          FOR UPDATE SKIP LOCKED
          LIMIT 1
     )
    RETURNING id, job_id, symbol, resolution, chunk_start, chunk_end, state, attempt,
              candles_written, requests, failure, started_at, finished_at
"""

_MARK_DONE = """
    UPDATE collection_job_chunks
       SET state = 'done', candles_written = $2, requests = $3, failure = NULL,
           finished_at = now()
     WHERE id = $1
"""

_MARK_SKIPPED = """
    UPDATE collection_job_chunks
       SET state = 'skipped', requests = $2, failure = NULL, finished_at = now()
     WHERE id = $1
"""

_MARK_FAILED = """
    UPDATE collection_job_chunks
       SET state = 'failed', failure = $2, requests = $3, finished_at = now()
     WHERE id = $1
"""

# Every chunk of a pair, across every job, still pending — not `running`, which a worker
# already claimed and `execute_chunk`'s own tracked-pair check is what stops from
# writing (`market-data-tracking` spec, "Kawałek nigdy nie zapisuje dla pary, której
# nikt nie zbiera").
_SKIP_PENDING_FOR_PAIR = """
    UPDATE collection_job_chunks
       SET state = 'skipped', finished_at = now()
     WHERE symbol = $1 AND resolution = $2 AND state = 'pending'
    RETURNING id
"""

# Every chunk of this job, for this pair, that is still pending and lies entirely at or
# before the boundary just discovered. `chunk_end <= boundary` is deliberately not
# `<`: a chunk touching the boundary exactly has nothing on its far side either.
_SKIP_BEYOND_HISTORY = """
    UPDATE collection_job_chunks
       SET state = 'skipped', finished_at = now()
     WHERE job_id = $1 AND symbol = $2 AND resolution = $3
       AND state = 'pending' AND chunk_end <= $4
    RETURNING id
"""

_INTERRUPT_OPEN_CHUNKS = """
    UPDATE collection_job_chunks
       SET state = 'interrupted', finished_at = now()
     WHERE state IN ('pending', 'running')
    RETURNING id
"""

_BUMP_JOB_ATTEMPT = """
    UPDATE collection_jobs SET attempt = attempt + 1 WHERE id = $1 RETURNING attempt
"""

# `FOR UPDATE` on both, and that is the whole race. `_CLAIM_PENDING_CHUNK` claims with
# `FOR UPDATE SKIP LOCKED`, so a chunk this transaction holds is one the runner skips
# rather than claims — without the lock, "nothing is open here" can be true when it is
# read and false by the time the delete lands, leaving a running chunk whose job is gone.
_LOCK_JOB = """
    SELECT id FROM collection_jobs WHERE id = $1 FOR UPDATE
"""

_LOCK_CHUNK_STATES = """
    SELECT state FROM collection_job_chunks WHERE job_id = $1 FOR UPDATE
"""

# No `ON DELETE CASCADE` on the chunks' foreign key (`0005_collection_jobs`), on purpose:
# this is the only place allowed to remove a chunk, and a cascade would put that fact in
# a migration nobody reads instead of here, beside the rest of these two tables' SQL.
_DELETE_CHUNKS_FOR_JOB = """
    DELETE FROM collection_job_chunks WHERE job_id = $1
"""

_DELETE_JOB = """
    DELETE FROM collection_jobs WHERE id = $1
"""

_RESET_RETRYABLE_CHUNKS = """
    UPDATE collection_job_chunks
       SET state = 'pending', attempt = $2, failure = NULL,
           started_at = NULL, finished_at = NULL
     WHERE job_id = $1 AND state = ANY($3::text[])
    RETURNING id
"""


def _chunk(row: asyncpg.Record) -> Chunk:
    return Chunk(
        id=row["id"],
        job_id=row["job_id"],
        symbol=row["symbol"],
        resolution=Resolution(row["resolution"]),
        chunk_start=row["chunk_start"],
        chunk_end=row["chunk_end"],
        state=ChunkState(row["state"]),
        attempt=row["attempt"],
        candles_written=row["candles_written"],
        requests=row["requests"],
        failure=row["failure"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
    )


async def create_job(
    conn: asyncpg.Connection, requested_from: datetime, plans: list[ChunkPlan]
) -> Job:
    """Record a job and the chunks it was planned into, as one write.

    `plans` may be empty — every pair in the decision was already fully covered — and
    the job is still created, so the operator's decision has a record even when there
    was nothing left to fetch for it.
    """
    async with conn.transaction():
        row = await fetch_one(conn, _INSERT_JOB, requested_from)
        job_id = row["id"]
        for plan in plans:
            await conn.execute(
                _INSERT_CHUNK,
                job_id,
                plan.symbol,
                plan.resolution.value,
                plan.chunk_start,
                plan.chunk_end,
            )
        chunks = [_chunk(r) for r in await conn.fetch(_SELECT_CHUNKS_FOR_JOB, job_id)]

    return Job(
        id=job_id,
        created_at=row["created_at"],
        requested_from=row["requested_from"],
        attempt=row["attempt"],
        chunks=chunks,
    )


async def read_job(conn: asyncpg.Connection, job_id: int) -> Job | None:
    """The whole job — every pair, every chunk. `None` if no job has this id."""
    row = await conn.fetchrow(_SELECT_JOB, job_id)
    if row is None:
        return None
    chunks = [_chunk(r) for r in await conn.fetch(_SELECT_CHUNKS_FOR_JOB, job_id)]
    return Job(
        id=row["id"],
        created_at=row["created_at"],
        requested_from=row["requested_from"],
        attempt=row["attempt"],
        chunks=chunks,
    )


async def list_jobs(
    conn: asyncpg.Connection,
    symbol: str | None = None,
    resolution: Resolution | None = None,
) -> list[JobPairView]:
    """Every job, narrowed to one row per pair it touched, newest job first.

    Filtering by pair does not hide a job's other pairs from existing — it only decides
    which jobs are worth returning at all. A row for a filtered-in job still carries only
    the chunks of the pair asked about, never chunks belonging to another pair the same
    job also covered; `read_job` is what shows a job whole.
    """
    ids = await conn.fetch(
        _SELECT_MATCHING_JOB_IDS, symbol, resolution.value if resolution else None
    )
    views: list[JobPairView] = []
    for row in ids:
        job = await read_job(conn, row["id"])
        if job is None:
            continue
        for view in narrow_to_pairs(job):
            if symbol is not None and view.symbol != symbol:
                continue
            if resolution is not None and view.resolution != resolution:
                continue
            views.append(view)
    return views


async def interrupt_orphaned_chunks(conn: asyncpg.Connection) -> int:
    """Flip every chunk left `pending` or `running` to `interrupted`.

    Called once at startup, before anything else touches the job tables. No runner
    survives a restart, so any chunk not yet settled at this moment was left mid-flight
    or waiting in line behind one — either way, nothing in this process is working it,
    and reporting it as still running would be a lie the next 30-second poll repeats.
    """
    rows = await conn.fetch(_INTERRUPT_OPEN_CHUNKS)
    return len(rows)


async def claim_pending_chunk(conn: asyncpg.Connection) -> Chunk | None:
    """Take the oldest pending chunk across every job, and mark it running.

    `FOR UPDATE SKIP LOCKED` is what lets more than one worker call this at once without
    two of them claiming the same chunk — the second simply skips the row the first is
    holding and finds the next.
    """
    row = await conn.fetchrow(_CLAIM_PENDING_CHUNK)
    return _chunk(row) if row else None


async def finish_chunk_done(
    conn: asyncpg.Connection, chunk_id: int, *, written: int, requests: int
) -> None:
    await conn.execute(_MARK_DONE, chunk_id, written, requests)


async def finish_chunk_skipped(conn: asyncpg.Connection, chunk_id: int, *, requests: int) -> None:
    """Beyond the provider's own history — not a failure. Recorded the same as a fill
    that reached `history_ended` without exhausting its bar budget."""
    await conn.execute(_MARK_SKIPPED, chunk_id, requests)


async def finish_chunk_failed(
    conn: asyncpg.Connection, chunk_id: int, *, failure: str, requests: int
) -> None:
    await conn.execute(_MARK_FAILED, chunk_id, failure, requests)


async def skip_pending_chunks_for_pair(
    conn: asyncpg.Connection, symbol: str, resolution: Resolution
) -> int:
    """Every not-yet-claimed chunk of a pair, across every job it belongs to, settled as
    skipped rather than run. Called right before deleting a pair's data, so nothing
    claims new work for a pair whose data is about to disappear. Returns how many were
    skipped.
    """
    rows = await conn.fetch(_SKIP_PENDING_FOR_PAIR, symbol, resolution.value)
    return len(rows)


async def skip_chunks_beyond_history(
    conn: asyncpg.Connection,
    job_id: int,
    symbol: str,
    resolution: Resolution,
    boundary: datetime,
) -> int:
    """Once one chunk discovers the provider's own boundary, every chunk still queued
    behind it — by construction older, by construction past that boundary, since chunks
    run newest-first (`plan.py`, `split_into_windows`) — is skipped without ever being
    claimed. Returns how many were skipped.
    """
    rows = await conn.fetch(_SKIP_BEYOND_HISTORY, job_id, symbol, resolution.value, boundary)
    return len(rows)


async def delete_job(conn: asyncpg.Connection, job_id: int) -> None:
    """Remove a job and its chunks from the history, leaving every candle alone.

    Deleting the record of work does not undo the work: the candles this job wrote, and
    the coverage that follows from them, stay exactly as they are (`market-data-jobs`
    spec, "Wpis historii zlecenia da się usunąć"). Removing data is
    `deletion.delete_pair_data`, which is a different operation and the one that leaves
    a trace of itself.

    Raises `UnknownJob` for an id nobody created and `JobStillRunning` while any chunk is
    `pending` or `running`. `pending` counts the same as `running` — it is a chunk the
    runner will claim in a moment, and its result would be written against a job that no
    longer exists.
    """
    async with conn.transaction():
        if await conn.fetchrow(_LOCK_JOB, job_id) is None:
            raise UnknownJob(f"no collection job with id {job_id}")

        states = [ChunkState(row["state"]) for row in await conn.fetch(_LOCK_CHUNK_STATES, job_id)]
        if any(state in OPEN_CHUNK_STATES for state in states):
            raise JobStillRunning(
                f"job {job_id} still has chunks pending or running — it cannot be removed "
                "from the history while a runner may work them"
            )

        await conn.execute(_DELETE_CHUNKS_FOR_JOB, job_id)
        await conn.execute(_DELETE_JOB, job_id)


async def retry_job(conn: asyncpg.Connection, job_id: int) -> Job:
    """Reset every failed or interrupted chunk of a job to `pending`, on a new attempt.

    Raises `UnknownJob` for an id nobody created, and `NothingToRetry` for a job with
    nothing to retry — succeeding outright, or still running. Both are refusals an
    operator can read the reason for; neither leaves the job touched.
    """
    job = await read_job(conn, job_id)
    if job is None:
        raise UnknownJob(f"no collection job with id {job_id}")
    if not job.failed_chunks:
        raise NothingToRetry(
            f"job {job_id} has no failed or interrupted chunk — nothing to retry"
        )

    async with conn.transaction():
        row = await fetch_one(conn, _BUMP_JOB_ATTEMPT, job_id)
        new_attempt = row["attempt"]
        await conn.fetch(
            _RESET_RETRYABLE_CHUNKS,
            job_id,
            new_attempt,
            [state.value for state in RETRYABLE_CHUNK_STATES],
        )

    retried = await read_job(conn, job_id)
    assert retried is not None  # the job cannot vanish under its own retry
    return retried
