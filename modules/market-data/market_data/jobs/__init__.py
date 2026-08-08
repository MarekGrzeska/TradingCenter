"""Collection jobs: a durable record of what backfill was asked for, and how it went.

`models.py` is the vocabulary and the one place a job's status is worked out from its
chunks. `store.py` is the only door to the two tables. `plan.py` turns "these pairs, from
this moment" into chunks a job can be made of, and prices that plan without running it.
`runner.py` works a job's chunks under the same fill budget as everything else this
module fetches with.
"""

from __future__ import annotations

from .models import Chunk, ChunkPlan, ChunkState, Job, JobPairView, JobStatus
from .plan import FutureRequest, JobEstimate, PairEstimate, estimate_job, plan_chunks
from .store import (
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
)

__all__ = [
    "Chunk",
    "ChunkPlan",
    "ChunkState",
    "FutureRequest",
    "Job",
    "JobEstimate",
    "JobPairView",
    "JobStatus",
    "NothingToRetry",
    "PairEstimate",
    "UnknownJob",
    "claim_pending_chunk",
    "create_job",
    "estimate_job",
    "finish_chunk_done",
    "finish_chunk_failed",
    "finish_chunk_skipped",
    "interrupt_orphaned_chunks",
    "list_jobs",
    "plan_chunks",
    "read_job",
    "retry_job",
]
