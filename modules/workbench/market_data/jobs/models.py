"""The vocabulary of a job, and the one place a job's status is worked out from its chunks."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel

from ..models import Resolution


class ChunkState(str, Enum):
    """One chunk's life. `interrupted` is reached only from `pending` or `running`, and only by this
    module's own startup: no runner survives a restart."""

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
    """A job's status, from its chunks' states alone. Any chunk still open means running — including
    a queued one, because a runner is what makes `pending` mean "about to happen"."""
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
    """(chunks settled, chunks total) — done and skipped both count as settled,
    the way a fill that found nothing further back is not a failure."""
    done = sum(1 for chunk in chunks if chunk.state in SETTLED_CHUNK_STATES)
    return done, len(chunks)


def _last_activity(chunks: list[Chunk], created_at: datetime) -> datetime:
    """When something last happened here — a chunk starting counts, not only one settling. A chunk
    working for forty minutes and one stuck for forty report the same numbers; only this separates them."""
    moments = [
        moment
        for chunk in chunks
        for moment in (chunk.finished_at, chunk.started_at)
        if moment is not None
    ]
    return max(moments) if moments else created_at


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
    def last_activity_at(self) -> datetime:
        return _last_activity(self.chunks, self.created_at)

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
    """One job, narrowed to one pair. `Job` itself is never narrowed: it stays the whole record for
    `GET /jobs/{id}` and for retry, which has to see every pair the job touched."""

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

    @property
    def last_activity_at(self) -> datetime:
        # This pair's own chunks only — another pair of the same job working away says
        # nothing about whether this one is moving.
        return _last_activity(self.chunks, self.created_at)


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
