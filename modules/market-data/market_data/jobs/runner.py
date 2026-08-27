"""Working a job's chunks, under the same fill budget as everything else. No runner survives the
process: a chunk still open when it stops is picked up by `store.interrupt_orphaned_chunks`."""

from __future__ import annotations

import asyncio
import logging

from ..errors import GatewayError
from ..gateway import GatewayHistory
from ..periods import periods_between
from ..store import commit_candles
from ..tracking import is_tracked
from .models import Chunk
from .store import (
    claim_pending_chunk,
    finish_chunk_done,
    finish_chunk_failed,
    finish_chunk_skipped,
    skip_chunks_beyond_history,
)

log = logging.getLogger(__name__)

# How long an idle worker waits before checking again. `notify()` wakes it immediately after a job
# is created, so this is only the fallback for a missed wake-up.
IDLE_POLL_SECONDS = 5.0

# How long a worker waits after failing to take work, and how far that grows. The cause is almost
# always the database, which comes back in minutes: retrying every five seconds buys 720 log lines.
FAILURE_BACKOFF_SECONDS = 5.0
MAX_FAILURE_BACKOFF_SECONDS = 60.0


async def execute_chunk(
    pool, history: GatewayHistory, chunk: Chunk, limiter: asyncio.Semaphore
) -> None:
    """Run one claimed chunk to a settled state — one gateway request, however deep. Both edges are
    named: `bars` counts candles and cannot bound a read in time, which `after` does."""
    bars = periods_between(chunk.resolution, chunk.chunk_start, chunk.chunk_end)
    try:
        async with limiter:
            page = await history.history(
                chunk.symbol,
                chunk.resolution,
                bars,
                before=chunk.chunk_end,
                after=chunk.chunk_start,
            )
    except GatewayError as err:
        async with pool.acquire() as conn:
            await finish_chunk_failed(conn, chunk.id, failure=str(err), requests=0)
        log.warning(
            "chunk %d (%s %s) failed: %s", chunk.id, chunk.symbol, chunk.resolution.value, err
        )
        return

    async with pool.acquire() as conn:
        # The pair may have been deleted while this chunk's request was in flight, and writing the
        # answer would resurrect data an operator just removed. Not narrower than "tracked".
        if not await is_tracked(conn, chunk.symbol, chunk.resolution):
            await finish_chunk_skipped(conn, chunk.id, requests=page.requests)
            log.info(
                "chunk %d (%s %s) skipped: pair no longer tracked",
                chunk.id,
                chunk.symbol,
                chunk.resolution.value,
            )
            return

        # Nothing older than this chunk's own window, whatever came back: a promise about what the
        # archive stores is not one to delegate. And nothing still forming.
        within = [
            c
            for c in page.candles
            if c.period_start >= chunk.chunk_start and not c.forming
        ]
        # The boundary is where the data ran out rather than where this chunk asked — a whole window
        # apart. A chunk that came back with nothing has an absence, not an edge.
        boundary = page.history_ended and bool(within)
        committed = await commit_candles(
            conn,
            within,
            symbol=chunk.symbol,
            resolution=chunk.resolution,
            # The requested window is what was verified, not only the span the candles occupy: an
            # exhaustive read of an empty stretch is still a stretch looked at, and edges must touch.
            covered_from=chunk.chunk_start,
            covered_to=chunk.chunk_end,
            history_ended=boundary,
            history_ends_at=within[0].period_start if boundary else None,
        )
        written = committed.written
        covered = committed.coverage

        await finish_chunk_done(conn, chunk.id, written=written, requests=page.requests)

        skipped = 0
        if covered.history_ends_at is not None:
            # Every chunk still queued behind this one is older by construction and past this
            # boundary, so it is settled in bulk. Against the boundary, not the merged range's start.
            skipped = await skip_chunks_beyond_history(
                conn, chunk.job_id, chunk.symbol, chunk.resolution, covered.history_ends_at
            )

    log.info(
        "chunk %d (%s %s) done: wrote %d candle(s) in %d request(s)%s%s",
        chunk.id,
        chunk.symbol,
        chunk.resolution.value,
        written,
        page.requests,
        ", provider history ended" if page.history_ended else "",
        f", {skipped} chunk(s) behind it skipped" if skipped else "",
    )


def _report_worker_death(worker: asyncio.Task) -> None:
    """Say so when a worker stops, because otherwise nothing does: a task that raises and is still
    referenced never reports it. Seen in production — eight chunks pending, no log line at all."""
    if worker.cancelled():
        return  # `stop()` — the normal way this ends.
    error = worker.exception()
    if error is not None:
        log.error("job runner worker %s died; no job will run", worker.get_name(), exc_info=error)
    else:
        log.error("job runner worker %s returned; no job will run", worker.get_name())


class JobRunner:
    """Works every job's pending chunks, worker count bounded by `concurrency`, all drawing from one
    shared fill budget. A worker that finds nothing waits until `notify()` or a short poll."""

    def __init__(
        self,
        pool,
        history: GatewayHistory,
        *,
        limiter: asyncio.Semaphore,
        concurrency: int = 1,
    ) -> None:
        self._pool = pool
        self._history = history
        self._limiter = limiter
        self._concurrency = concurrency
        self._wake = asyncio.Event()
        self._workers: list[asyncio.Task] = []

    def notify(self) -> None:
        self._wake.set()

    async def start(self) -> None:
        self._workers = [
            asyncio.create_task(self._worker_loop(f"job-runner-{n}"), name=f"job-runner-{n}")
            for n in range(self._concurrency)
        ]
        for worker in self._workers:
            worker.add_done_callback(_report_worker_death)

    async def stop(self) -> None:
        for worker in self._workers:
            worker.cancel()
        for worker in self._workers:
            try:
                await worker
            except asyncio.CancelledError:
                pass
        self._workers = []

    async def _worker_loop(self, name: str) -> None:
        """Take work, do it, repeat. Two different failures: a chunk that blows up is one thing to
        retry, while a failure taking work ends collection with nothing written anywhere."""
        backoff = FAILURE_BACKOFF_SECONDS
        while True:
            try:
                async with self._pool.acquire() as conn:
                    chunk = await claim_pending_chunk(conn)
                backoff = FAILURE_BACKOFF_SECONDS

                if chunk is None:
                    self._wake.clear()
                    try:
                        await asyncio.wait_for(self._wake.wait(), timeout=IDLE_POLL_SECONDS)
                    except TimeoutError:
                        pass
                    continue
            except asyncio.CancelledError:
                raise
            except Exception:
                # Nothing was claimed, so there is nothing to settle as failed. Waiting longer each
                # time keeps an hour-long outage from filling the log with one line 720 times.
                log.exception(
                    "job runner worker %s could not take work; trying again in %ss", name, backoff
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, MAX_FAILURE_BACKOFF_SECONDS)
                continue

            try:
                await execute_chunk(self._pool, self._history, chunk, self._limiter)
            except asyncio.CancelledError:
                raise
            except Exception as err:
                # A bug here must cost this one chunk, not silence a worker permanently
                # — the same reasoning as `Ingest`'s own loop around a pair's feed.
                log.exception(
                    "chunk %d (%s %s) raised while executing",
                    chunk.id,
                    chunk.symbol,
                    chunk.resolution.value,
                )
                # And it must cost the chunk visibly: anything past `execute_chunk`'s own handling
                # would leave it `running` with nobody running it, and no worker re-claims one.
                await self._fail_orphan(chunk, err)

    async def _fail_orphan(self, chunk: Chunk, err: Exception) -> None:
        """Settle a chunk whose execution raised past `execute_chunk`. Best effort by nature: the
        likeliest cause is the database, and this needs the database — a failure leaves it for startup."""
        try:
            async with self._pool.acquire() as conn:
                await finish_chunk_failed(
                    conn, chunk.id, failure=f"{type(err).__name__}: {err}", requests=0
                )
        except Exception:
            log.exception("could not record chunk %d as failed", chunk.id)
