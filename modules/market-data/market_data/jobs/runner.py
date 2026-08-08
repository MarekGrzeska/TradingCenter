"""Working a job's chunks, under the same fill budget as everything else this module
fetches with.

Nothing here decides what a chunk covers — that is `plan.py`. This turns one claimed
chunk into a gateway request and a settled outcome, and loops doing that for as long as
there is work and the process is alive. No runner survives past that: a chunk still
`pending` or `running` when the process stops is picked up by
`store.interrupt_orphaned_chunks` at the next start, not resumed here.
"""

from __future__ import annotations

import asyncio
import logging

from ..coverage import record_coverage
from ..errors import GatewayError
from ..gateway import GatewayHistory
from ..models import Resolution
from ..periods import periods_between
from ..rollups import refresh_all
from ..store import write_candles
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

# How long an idle worker waits before checking again. `JobRunner.notify()` wakes it
# immediately after a job is created; this is only the fallback for a missed wake-up,
# so it can afford to be unhurried.
IDLE_POLL_SECONDS = 5.0


async def execute_chunk(
    pool, history: GatewayHistory, chunk: Chunk, limiter: asyncio.Semaphore
) -> None:
    """Run one claimed chunk to a settled state.

    One gateway request, however deep the window: `before=chunk.chunk_end` anchors it,
    and `bars` is sized to the window exactly, so the gateway's own internal paging is
    what reaches back through it — this module does not page a second time
    (`capital-market-data` spec, "Historia jest stronicowana poza limit providera").

    Both edges are named, and the older one is the load-bearing half. `bars` counts
    *candles*, while `periods_between` counts *calendar periods* — for an instrument
    shut part of the week the two differ by half again, and a chunk asking for a
    January-to-August window's worth of bars was quietly handed candles reaching back to
    the previous autumn. `after=chunk.chunk_start` says the bound in time, which a count
    cannot; the filter below is the same promise kept locally, so this module never
    depends on the gateway having honoured it.

    A refusal or an unreachable gateway settles the chunk as `failed`, named, and stops
    there — it does not raise, because one chunk's failure must not take a worker down
    with it (`market-data-jobs` spec, "Nieudany kawałek nie przerywa zlecenia").
    """
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
        # The pair may have been deleted while this chunk's request was in flight — the
        # gateway does not know that, so its answer still arrives, and writing it would
        # resurrect data an operator just removed (`market-data-tracking` spec, "Kawałek
        # nigdy nie zapisuje dla pary, której nikt nie zbiera"). Not narrower than
        # "tracked": an untracked-but-not-deleted pair must not gain new candles either.
        if not await is_tracked(conn, chunk.symbol, chunk.resolution):
            await finish_chunk_skipped(conn, chunk.id, requests=page.requests)
            log.info(
                "chunk %d (%s %s) skipped: pair no longer tracked",
                chunk.id,
                chunk.symbol,
                chunk.resolution.value,
            )
            return

        # Nothing older than this chunk's own window, whatever came back. The gateway
        # is asked to bound the read and does, but a promise about what the archive
        # stores is not one to delegate.
        within = [c for c in page.candles if c.period_start >= chunk.chunk_start]
        written = await write_candles(conn, within) if within else 0
        # The requested window is what was verified, not only the span the candles
        # happen to occupy — an exhaustive read of an empty stretch is still a stretch
        # looked at, and using the requested edges keeps neighbouring chunks' coverage
        # touching with no seam between them.
        covered = await record_coverage(
            conn,
            chunk.symbol,
            chunk.resolution,
            chunk.chunk_start,
            chunk.chunk_end,
            history_ended=page.history_ended,
        )
        if within and chunk.resolution is Resolution.MINUTE:
            # Over what was actually stored, not what arrived — rebuilding a bucket from
            # minutes that were filtered out would derive a candle with no source.
            await refresh_all(conn, chunk.symbol, within[0].period_start, within[-1].period_start)

        await finish_chunk_done(conn, chunk.id, written=written, requests=page.requests)

        skipped = 0
        if page.history_ended:
            # Every chunk still queued behind this one — by construction older, by
            # construction past this boundary, since chunks run newest-first
            # (`plan.py`) — is settled here in bulk rather than each spending its own
            # request to rediscover the same edge.
            skipped = await skip_chunks_beyond_history(
                conn, chunk.job_id, chunk.symbol, chunk.resolution, covered.range_start
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


class JobRunner:
    """Works every job's pending chunks, worker count bounded by `concurrency`, all of
    them drawing from one shared fill budget with the rest of this module.

    A worker that finds nothing pending waits — `notify()` (called right after a job is
    created) wakes every idle worker immediately, and a short poll is only the fallback
    for a wake missed between a worker checking and going to sleep.
    """

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
            asyncio.create_task(self._worker_loop(), name=f"job-runner-{n}")
            for n in range(self._concurrency)
        ]

    async def stop(self) -> None:
        for worker in self._workers:
            worker.cancel()
        for worker in self._workers:
            try:
                await worker
            except asyncio.CancelledError:
                pass
        self._workers = []

    async def _worker_loop(self) -> None:
        while True:
            async with self._pool.acquire() as conn:
                chunk = await claim_pending_chunk(conn)

            if chunk is None:
                self._wake.clear()
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=IDLE_POLL_SECONDS)
                except TimeoutError:
                    pass
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
                # And it must cost the chunk *visibly*. `execute_chunk` names its own
                # gateway failures, but anything past that — a write that hit the
                # database wrong, a bug in this module — would otherwise leave the chunk
                # `running` with nobody running it: no worker re-claims a running chunk,
                # `retry_job` will not touch one, and the job reads as forever in
                # progress until the next restart sweeps it. Settling it as `failed`
                # here is what makes it retryable instead.
                await self._fail_orphan(chunk, err)

    async def _fail_orphan(self, chunk: Chunk, err: Exception) -> None:
        """Settle a chunk whose execution raised past `execute_chunk`'s own handling.

        Best effort by nature: the likeliest cause is the database itself, and this
        needs the database to record anything. A failure here leaves the chunk for
        `interrupt_orphaned_chunks` at the next start, which is where it would have been
        anyway — never a reason to take the worker down with it.
        """
        try:
            async with self._pool.acquire() as conn:
                await finish_chunk_failed(
                    conn, chunk.id, failure=f"{type(err).__name__}: {err}", requests=0
                )
        except Exception:
            log.exception("could not record chunk %d as failed", chunk.id)
