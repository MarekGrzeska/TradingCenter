"""What a collection job is, and the one rule for working out how it is going.

A job's status is never stored — it is derived from its chunks, every time. Two sources
of truth for the same fact drift apart exactly when a process dies between writing one
and the other, and a job's status is read most often right after the kind of restart
that could cause that.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel

from ..models import Resolution


class ChunkState(str, Enum):
    """One chunk's life. `interrupted` is reached only from `pending` or `running`, and
    only by this module's own startup — no runner survives a restart, so anything not
    yet settled at that moment was orphaned, not merely delayed."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    # Beyond the provider's own history — not a failure, the same distinction
    # `history_ended` makes for a single fill.
    SKIPPED = "skipped"
    INTERRUPTED = "interrupted"


# Chunks a runner may still pick up or is presently holding. Restart-flips these to
# `interrupted`, because nothing in the process can be holding one after it.
OPEN_CHUNK_STATES = frozenset({ChunkState.PENDING, ChunkState.RUNNING})

# Chunks a retry may take on — never `pending` or `running`, which a retry would race
# against whatever is already working them.
RETRYABLE_CHUNK_STATES = frozenset({ChunkState.FAILED, ChunkState.INTERRUPTED})

SETTLED_CHUNK_STATES = frozenset({ChunkState.DONE, ChunkState.SKIPPED})


class JobStatus(str, Enum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


def derive_status(states: list[ChunkState]) -> JobStatus:
    """A job's status, from its chunks' states alone.

    Any chunk still open means the job is running — including one merely queued,
    because a runner is what makes `pending` mean "about to happen" rather than "stuck".
    Once nothing is open, the job is done in some shape: fully, partially — some
    settled, some not — or not at all.
    """
    if not states:
        return JobStatus.SUCCEEDED
    if any(state in OPEN_CHUNK_STATES for state in states):
        return JobStatus.RUNNING

    succeeded = sum(1 for state in states if state in SETTLED_CHUNK_STATES)
    failed = sum(1 for state in states if state is ChunkState.FAILED)
    interrupted = sum(1 for state in states if state is ChunkState.INTERRUPTED)

    if failed == 0 and interrupted == 0:
        return JobStatus.SUCCEEDED
    if succeeded > 0:
        return JobStatus.PARTIAL
    if failed > 0:
        return JobStatus.FAILED
    return JobStatus.INTERRUPTED


class ChunkPlan(BaseModel):
    """One chunk's window, before it has an id — what `plan.py` hands to `create_job`."""

    symbol: str
    resolution: Resolution
    chunk_start: datetime
    chunk_end: datetime


class Chunk(BaseModel):
    """One pair, one window, one gateway request's worth of work."""

    id: int
    job_id: int
    symbol: str
    resolution: Resolution
    chunk_start: datetime
    chunk_end: datetime
    state: ChunkState
    attempt: int
    candles_written: int
    requests: int
    failure: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


def _status(chunks: list[Chunk]) -> JobStatus:
    return derive_status([chunk.state for chunk in chunks])


def _candles_written(chunks: list[Chunk]) -> int:
    return sum(chunk.candles_written for chunk in chunks)


def _progress(chunks: list[Chunk]) -> tuple[int, int]:
    """(kawałki ukończone, kawałki wszystkie) — done and skipped both count as settled,
    the way a fill that found nothing further back is not a failure."""
    done = sum(1 for chunk in chunks if chunk.state in SETTLED_CHUNK_STATES)
    return done, len(chunks)


def _running_pair(chunks: list[Chunk]) -> tuple[str, Resolution] | None:
    for chunk in chunks:
        if chunk.state is ChunkState.RUNNING:
            return chunk.symbol, chunk.resolution
    return None


def _failed_chunks(chunks: list[Chunk]) -> list[Chunk]:
    return [chunk for chunk in chunks if chunk.state in (ChunkState.FAILED, ChunkState.INTERRUPTED)]


class Job(BaseModel):
    """A whole job: every pair and every chunk it was asked to cover."""

    id: int
    created_at: datetime
    requested_from: datetime
    attempt: int
    chunks: list[Chunk]

    @property
    def status(self) -> JobStatus:
        return _status(self.chunks)

    @property
    def candles_written(self) -> int:
        return _candles_written(self.chunks)

    @property
    def progress(self) -> tuple[int, int]:
        return _progress(self.chunks)

    @property
    def running_pair(self) -> tuple[str, Resolution] | None:
        return _running_pair(self.chunks)

    @property
    def failed_chunks(self) -> list[Chunk]:
        return _failed_chunks(self.chunks)

    @property
    def pairs(self) -> set[tuple[str, Resolution]]:
        return {(chunk.symbol, chunk.resolution) for chunk in self.chunks}


class JobPairView(BaseModel):
    """One job, narrowed to one pair — what `terminal-collection-history` actually reads.

    A job created for four pairs is four of these once narrowed, one per pair, each with
    only that pair's chunks and a status derived from just them. `Job` itself is never
    narrowed this way; it stays the whole record for `GET /jobs/{id}` and for retry,
    which has to see every pair a job touched to know what it is retrying.
    """

    job_id: int
    symbol: str
    resolution: Resolution
    created_at: datetime
    requested_from: datetime
    attempt: int
    chunks: list[Chunk]

    @property
    def status(self) -> JobStatus:
        return _status(self.chunks)

    @property
    def candles_written(self) -> int:
        return _candles_written(self.chunks)

    @property
    def progress(self) -> tuple[int, int]:
        return _progress(self.chunks)


def narrow_to_pairs(job: Job) -> list[JobPairView]:
    """Every pair a job touched, each with only its own chunks."""
    views: dict[tuple[str, Resolution], list[Chunk]] = {}
    for chunk in job.chunks:
        views.setdefault((chunk.symbol, chunk.resolution), []).append(chunk)
    return [
        JobPairView(
            job_id=job.id,
            symbol=symbol,
            resolution=resolution,
            created_at=job.created_at,
            requested_from=job.requested_from,
            attempt=job.attempt,
            chunks=chunks,
        )
        for (symbol, resolution), chunks in views.items()
    ]
