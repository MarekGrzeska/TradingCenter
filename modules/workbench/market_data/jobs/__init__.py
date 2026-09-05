"""Collection jobs: a durable record of what backfill was asked for, and how it went. `store.py` is
the only door to the two tables, `plan.py` makes chunks, `runner.py` works them under the fill budget."""

from __future__ import annotations

from .models import Chunk, ChunkPlan, ChunkState, Job, JobPairView, JobStatus
from .plan import FutureRequest, JobEstimate, PairEstimate, estimate_job, plan_chunks
from .runner import JobRunner, execute_chunk
from .store import (
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
    skip_pending_chunks_for_pair,
)

__all__ = [
    "Chunk",
    "ChunkPlan",
    "ChunkState",
    "FutureRequest",
    "Job",
    "JobEstimate",
    "JobPairView",
    "JobRunner",
    "JobStatus",
    "JobStillRunning",
    "NothingToRetry",
    "PairEstimate",
    "UnknownJob",
    "claim_pending_chunk",
    "create_job",
    "delete_job",
    "estimate_job",
    "execute_chunk",
    "finish_chunk_done",
    "finish_chunk_failed",
    "finish_chunk_skipped",
    "interrupt_orphaned_chunks",
    "list_jobs",
    "plan_chunks",
    "read_job",
    "retry_job",
    "skip_chunks_beyond_history",
    "skip_pending_chunks_for_pair",
]
