"""jobs/runner.py: turning a claimed chunk into a settled outcome, and the loop that
keeps doing that.

Group 4 of rework-instrument-collection.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

import pytest

from market_data.coverage import read_coverage
from market_data.errors import GatewayRefused, GatewayUnreachable
from market_data.gateway import HistoryPage
from market_data.jobs.models import ChunkPlan, ChunkState
from market_data.jobs.runner import JobRunner, _report_worker_death, execute_chunk
from market_data.jobs.store import claim_pending_chunk, create_job, read_job
from market_data.models import Candle, CandleSource, Resolution
from market_data.store import read_candles
from market_data.tracking import track

NOW = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)
LIMIT = 20


def plan(symbol: str = "US100", resolution: Resolution = Resolution.MINUTE, **overrides) -> ChunkPlan:
    values = {
        "symbol": symbol,
        "resolution": resolution,
        "chunk_start": NOW - timedelta(days=1),
        "chunk_end": NOW,
        **overrides,
    }
    return ChunkPlan(**values)


def minute_candle(offset: int, symbol: str = "US100", **overrides):
    return Candle(
        **{
            "symbol": symbol,
            "resolution": Resolution.MINUTE,
            "period_start": NOW - timedelta(minutes=offset),
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 10.0,
            "source": CandleSource.HISTORY,
            **overrides,
        }
    )


class FakeHistory:
    """A gateway history reader that records what it was anchored on and answers with
    what it was given — the runner equivalent of `test_ingest.py`'s own fake."""

    def __init__(self, candles=None, requests: int = 1, history_ended: bool = False, error=None):
        self.candles = candles if candles is not None else []
        self.requests = requests
        self.history_ended = history_ended
        self.error = error
        self.calls: list[tuple[str, Resolution, int, datetime | None]] = []
        # The `after` of each call, kept beside `calls` so assertions written before a
        # floor existed stay readable.
        self.floors: list[datetime | None] = []

    async def history(
        self,
        symbol: str,
        resolution: Resolution,
        bars: int,
        before: datetime | None = None,
        after: datetime | None = None,
    ) -> HistoryPage:
        self.calls.append((symbol, resolution, bars, before))
        self.floors.append(after)
        if self.error is not None:
            raise self.error
        return HistoryPage(
            symbol=symbol,
            resolution=resolution,
            candles=sorted(self.candles, key=lambda c: c.period_start),
            requested=bars,
            requests=self.requests,
            history_ended=self.history_ended,
        )


@pytest.fixture
async def pool(migrated_url: str):
    from market_data.db import pool as make_pool

    async with make_pool(migrated_url, max_size=5) as created:
        async with created.acquire() as conn:
            await conn.execute(
                "TRUNCATE candles, derived_candles, tracked_pairs, coverage_ranges, "
                "collection_jobs, collection_job_chunks, pair_deletions"
            )
        yield created


async def _tracked(pool, symbol: str = "US100", resolution: Resolution = Resolution.MINUTE):
    async with pool.acquire() as conn:
        await track(conn, symbol, resolution, LIMIT, collect_from=NOW - timedelta(days=3650))


# --- execute_chunk: the happy path ----------------------------------------------------


async def test_a_successful_chunk_writes_candles_and_settles_done(pool) -> None:
    await _tracked(pool)
    async with pool.acquire() as conn:
        job = await create_job(conn, NOW, [plan(chunk_start=NOW - timedelta(hours=1), chunk_end=NOW)])
        chunk = await claim_pending_chunk(conn)

    history = FakeHistory([minute_candle(1), minute_candle(2)], requests=1)
    await execute_chunk(pool, history, chunk, asyncio.Semaphore(1))

    async with pool.acquire() as conn:
        reread = await read_job(conn, job.id)
        candles = await read_candles(conn, "US100", Resolution.MINUTE)

    assert reread.chunks[0].state is ChunkState.DONE
    assert reread.chunks[0].candles_written == 2
    assert len(candles) == 2


async def test_the_request_is_anchored_on_the_chunk_end(pool) -> None:
    await _tracked(pool)
    chunk_start = NOW - timedelta(days=10)
    chunk_end = NOW - timedelta(days=5)
    async with pool.acquire() as conn:
        await create_job(conn, NOW, [plan(chunk_start=chunk_start, chunk_end=chunk_end)])
        chunk = await claim_pending_chunk(conn)

    history = FakeHistory([])
    await execute_chunk(pool, history, chunk, asyncio.Semaphore(1))

    [(symbol, resolution, _bars, before)] = history.calls
    assert before == chunk_end
    assert symbol == "US100" and resolution is Resolution.MINUTE


async def test_a_chunk_with_nothing_returned_is_still_done_not_failed(pool) -> None:
    # A window that happened to hold no candles (a shut market, say) is a real answer,
    # not a problem — `written=0` is a legitimate outcome of `done`.
    await _tracked(pool)
    async with pool.acquire() as conn:
        await create_job(conn, NOW, [plan(chunk_start=NOW - timedelta(hours=1), chunk_end=NOW)])
        chunk = await claim_pending_chunk(conn)

    await execute_chunk(pool, FakeHistory([]), chunk, asyncio.Semaphore(1))

    async with pool.acquire() as conn:
        reread = await read_job(conn, chunk.job_id)
    assert reread.chunks[0].state is ChunkState.DONE
    assert reread.chunks[0].candles_written == 0


async def test_a_chunk_names_its_own_window_as_the_floor(pool) -> None:
    await _tracked(pool)
    chunk_start = NOW - timedelta(hours=1)
    async with pool.acquire() as conn:
        await create_job(conn, NOW, [plan(chunk_start=chunk_start, chunk_end=NOW)])
        chunk = await claim_pending_chunk(conn)

    history = FakeHistory([])
    await execute_chunk(pool, history, chunk, asyncio.Semaphore(1))

    assert history.floors == [chunk_start]


async def test_a_chunk_stores_nothing_older_than_its_own_window(pool) -> None:
    """The bug this exists for, in the shape that let it through.

    `bars` counts candles and `periods_between` counts calendar periods, so for an
    instrument shut part of the week the gateway hands back candles reaching well past
    the window that was asked for. Every test here used to assert what was *requested*;
    none asserted what landed in the archive, which is the only place the overshoot was
    ever visible.
    """
    await _tracked(pool)
    chunk_start = NOW - timedelta(hours=1)
    async with pool.acquire() as conn:
        await create_job(conn, NOW, [plan(chunk_start=chunk_start, chunk_end=NOW)])
        chunk = await claim_pending_chunk(conn)

    # Two inside the window, one two hours old — before the chunk ever begins.
    history = FakeHistory([minute_candle(1), minute_candle(30), minute_candle(120)])
    await execute_chunk(pool, history, chunk, asyncio.Semaphore(1))

    async with pool.acquire() as conn:
        stored = await read_candles(conn, "US100", Resolution.MINUTE)
        reread = await read_job(conn, chunk.job_id)

    assert [c.period_start for c in stored] == [NOW - timedelta(minutes=30), NOW - timedelta(minutes=1)]
    # And the count the job reports is what it actually kept, not what arrived.
    assert reread.chunks[0].candles_written == 2


async def test_a_chunk_for_a_pair_deleted_mid_flight_writes_nothing(pool) -> None:
    """The gateway answer for a chunk claimed before deletion still arrives after it —
    `delete-archived-pair-data` design.md, "Kawałek nigdy nie zapisuje dla pary, której
    nikt nie zbiera"."""
    from market_data.deletion import close_for_deletion, delete_pair_data

    await _tracked(pool)
    async with pool.acquire() as conn:
        await create_job(conn, NOW, [plan(chunk_start=NOW - timedelta(hours=1), chunk_end=NOW)])
        chunk = await claim_pending_chunk(conn)
        await close_for_deletion(conn, "US100", Resolution.MINUTE)
        await delete_pair_data(conn, "US100", Resolution.MINUTE)

    await execute_chunk(pool, FakeHistory([minute_candle(1)]), chunk, asyncio.Semaphore(1))

    async with pool.acquire() as conn:
        reread = await read_job(conn, chunk.job_id)
        candles = await read_candles(conn, "US100", Resolution.MINUTE)
    assert reread.chunks[0].state is ChunkState.SKIPPED
    assert candles == []


async def test_a_chunk_for_a_pair_merely_untracked_mid_flight_also_writes_nothing(
    pool,
) -> None:
    from market_data.tracking import untrack

    await _tracked(pool)
    async with pool.acquire() as conn:
        await create_job(conn, NOW, [plan(chunk_start=NOW - timedelta(hours=1), chunk_end=NOW)])
        chunk = await claim_pending_chunk(conn)
        await untrack(conn, "US100", Resolution.MINUTE)

    await execute_chunk(pool, FakeHistory([minute_candle(1)]), chunk, asyncio.Semaphore(1))

    async with pool.acquire() as conn:
        candles = await read_candles(conn, "US100", Resolution.MINUTE)
    assert candles == []


async def test_the_full_window_is_recorded_as_covered_not_only_where_candles_landed(
    pool,
) -> None:
    await _tracked(pool)
    chunk_start = NOW - timedelta(hours=2)
    chunk_end = NOW
    async with pool.acquire() as conn:
        await create_job(conn, NOW, [plan(chunk_start=chunk_start, chunk_end=chunk_end)])
        chunk = await claim_pending_chunk(conn)

    # Only one candle, in the middle of the window — the market was thin, not the
    # window unverified.
    await execute_chunk(
        pool, FakeHistory([minute_candle(30)]), chunk, asyncio.Semaphore(1)
    )

    async with pool.acquire() as conn:
        [coverage] = await read_coverage(conn, "US100", Resolution.MINUTE)
    assert coverage.range_start == chunk_start
    assert coverage.range_end == chunk_end


# --- execute_chunk: failure --------------------------------------------------------------


async def test_a_refusal_settles_the_chunk_as_failed_with_the_reason(pool) -> None:
    await _tracked(pool)
    async with pool.acquire() as conn:
        await create_job(conn, NOW, [plan(chunk_start=NOW - timedelta(hours=1), chunk_end=NOW)])
        chunk = await claim_pending_chunk(conn)

    error = GatewayRefused(502, "capital.com said no")
    await execute_chunk(pool, FakeHistory(error=error), chunk, asyncio.Semaphore(1))

    async with pool.acquire() as conn:
        reread = await read_job(conn, chunk.job_id)
    assert reread.chunks[0].state is ChunkState.FAILED
    assert "capital.com said no" in reread.chunks[0].failure


async def test_an_unreachable_gateway_also_settles_as_failed(pool) -> None:
    await _tracked(pool)
    async with pool.acquire() as conn:
        await create_job(conn, NOW, [plan(chunk_start=NOW - timedelta(hours=1), chunk_end=NOW)])
        chunk = await claim_pending_chunk(conn)

    await execute_chunk(
        pool, FakeHistory(error=GatewayUnreachable("no answer")), chunk, asyncio.Semaphore(1)
    )

    async with pool.acquire() as conn:
        reread = await read_job(conn, chunk.job_id)
    assert reread.chunks[0].state is ChunkState.FAILED


async def test_a_failed_chunk_does_not_raise_out_of_execute_chunk(pool) -> None:
    # The whole reason execute_chunk swallows GatewayError: one chunk's failure must
    # not take a caller looping over many chunks down with it.
    await _tracked(pool)
    async with pool.acquire() as conn:
        await create_job(conn, NOW, [plan(chunk_start=NOW - timedelta(hours=1), chunk_end=NOW)])
        chunk = await claim_pending_chunk(conn)

    await execute_chunk(
        pool, FakeHistory(error=GatewayUnreachable("no answer")), chunk, asyncio.Semaphore(1)
    )  # must not raise


# --- execute_chunk: discovering the provider's boundary ---------------------------------


async def test_history_ended_bulk_skips_older_pending_chunks_of_the_same_pair(pool) -> None:
    await _tracked(pool)
    newest = plan(chunk_start=NOW - timedelta(days=1), chunk_end=NOW)
    boundary_chunk = plan(chunk_start=NOW - timedelta(days=2), chunk_end=NOW - timedelta(days=1))
    older = plan(chunk_start=NOW - timedelta(days=3), chunk_end=NOW - timedelta(days=2))
    async with pool.acquire() as conn:
        job = await create_job(conn, NOW, [newest, boundary_chunk, older])
        first_claimed = await claim_pending_chunk(conn)  # newest, per insertion order

    # The newest chunk finds real data — this is not where the boundary lies.
    await execute_chunk(pool, FakeHistory([minute_candle(1)]), first_claimed, asyncio.Semaphore(1))

    async with pool.acquire() as conn:
        second_claimed = await claim_pending_chunk(conn)  # boundary_chunk

    # This one discovers the end of history.
    await execute_chunk(
        pool, FakeHistory([], history_ended=True), second_claimed, asyncio.Semaphore(1)
    )

    async with pool.acquire() as conn:
        reread = await read_job(conn, job.id)
    by_window = {(c.chunk_start, c.chunk_end): c.state for c in reread.chunks}
    assert by_window[(boundary_chunk.chunk_start, boundary_chunk.chunk_end)] is ChunkState.DONE
    assert by_window[(older.chunk_start, older.chunk_end)] is ChunkState.SKIPPED


async def test_a_pair_untouched_by_the_boundary_is_not_skipped(pool) -> None:
    await _tracked(pool, "US100", Resolution.MINUTE)
    await _tracked(pool, "US100", Resolution.HOUR)
    minute_chunk = plan(resolution=Resolution.MINUTE, chunk_start=NOW - timedelta(days=1), chunk_end=NOW)
    hour_chunk = plan(resolution=Resolution.HOUR, chunk_start=NOW - timedelta(days=400), chunk_end=NOW)
    async with pool.acquire() as conn:
        await create_job(conn, NOW, [minute_chunk, hour_chunk])
        claimed = await claim_pending_chunk(conn)
        assert claimed.resolution is Resolution.MINUTE

    await execute_chunk(pool, FakeHistory([], history_ended=True), claimed, asyncio.Semaphore(1))

    async with pool.acquire() as conn:
        [remaining] = await conn.fetch(
            "SELECT state FROM collection_job_chunks WHERE resolution = 'HOUR'"
        )
    assert remaining["state"] == "pending"


# --- the worker loop ------------------------------------------------------------------


async def test_the_runner_claims_and_settles_a_pending_chunk(pool) -> None:
    await _tracked(pool)
    async with pool.acquire() as conn:
        job = await create_job(conn, NOW, [plan(chunk_start=NOW - timedelta(hours=1), chunk_end=NOW)])

    runner = JobRunner(pool, FakeHistory([minute_candle(1)]), limiter=asyncio.Semaphore(1))
    await runner.start()
    try:
        await asyncio.sleep(0.1)
        async with pool.acquire() as conn:
            reread = await read_job(conn, job.id)
    finally:
        await runner.stop()

    assert reread.chunks[0].state is ChunkState.DONE


async def test_notify_wakes_an_idle_worker_without_waiting_for_the_poll(pool) -> None:
    runner = JobRunner(pool, FakeHistory([]), limiter=asyncio.Semaphore(1))
    await runner.start()
    try:
        await asyncio.sleep(0.05)  # let the worker find nothing and go idle

        await _tracked(pool)
        async with pool.acquire() as conn:
            job = await create_job(
                conn, NOW, [plan(chunk_start=NOW - timedelta(hours=1), chunk_end=NOW)]
            )
        runner.notify()

        await asyncio.sleep(0.1)
        async with pool.acquire() as conn:
            reread = await read_job(conn, job.id)
    finally:
        await runner.stop()

    assert reread.status.value == "succeeded"


async def test_stopping_the_runner_ends_its_workers(pool) -> None:
    runner = JobRunner(pool, FakeHistory([]), limiter=asyncio.Semaphore(1))
    await runner.start()
    await runner.stop()
    assert all(worker.done() for worker in runner._workers) or runner._workers == []


async def test_a_chunk_whose_execution_raises_settles_failed_rather_than_stuck_running(
    pool,
) -> None:
    """A chunk left `running` is worse than a chunk marked `failed`: no worker re-claims
    one, `retry_job` refuses to touch one, and the job reads as forever in progress. So
    anything raising past `execute_chunk`'s own gateway handling still has to settle."""
    await _tracked(pool)
    async with pool.acquire() as conn:
        job = await create_job(
            conn, NOW, [plan(chunk_start=NOW - timedelta(hours=1), chunk_end=NOW)]
        )

    class Exploding:
        async def history(self, *args, **kwargs):
            # Not a GatewayError — `execute_chunk` names those itself. This stands in for
            # the rest: a bad write, a bug in this module.
            raise RuntimeError("something nobody planned for")

    runner = JobRunner(pool, Exploding(), limiter=asyncio.Semaphore(1))
    await runner.start()
    try:
        await asyncio.sleep(0.1)
        async with pool.acquire() as conn:
            reread = await read_job(conn, job.id)
    finally:
        await runner.stop()

    assert reread.chunks[0].state is ChunkState.FAILED
    assert "something nobody planned for" in reread.chunks[0].failure
    # And being failed is what makes it retryable at all.
    assert reread.failed_chunks


async def test_a_worker_keeps_going_after_one_chunk_raises(pool) -> None:
    """One chunk's unplanned failure must not silence the worker for the rest."""
    await _tracked(pool)
    async with pool.acquire() as conn:
        job = await create_job(
            conn,
            NOW,
            [
                plan(chunk_start=NOW - timedelta(hours=1), chunk_end=NOW),
                plan(chunk_start=NOW - timedelta(hours=2), chunk_end=NOW - timedelta(hours=1)),
            ],
        )

    class ExplodingOnce:
        def __init__(self) -> None:
            self.calls = 0

        async def history(self, symbol, resolution, bars, before=None, after=None) -> HistoryPage:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("the first one blew up")
            return HistoryPage(
                symbol=symbol,
                resolution=resolution,
                candles=[],
                requested=bars,
                requests=1,
                history_ended=False,
            )

    runner = JobRunner(pool, ExplodingOnce(), limiter=asyncio.Semaphore(1))
    await runner.start()
    try:
        await asyncio.sleep(0.2)
        async with pool.acquire() as conn:
            reread = await read_job(conn, job.id)
    finally:
        await runner.stop()

    states = {chunk.state for chunk in reread.chunks}
    assert states == {ChunkState.FAILED, ChunkState.DONE}


# --- taking work is where the loop used to die ----------------------------------------


class _FlakyPool:
    """A pool that refuses to hand out a connection until it is told to stop.

    Stands in for the failure the loop was blind to: not the gateway, not the chunk, but
    the database underneath `claim_pending_chunk`. Before, one of these ended the worker
    for the life of the process.
    """

    def __init__(self, real, failures: int) -> None:
        self._real = real
        self.remaining = failures
        self.attempts = 0

    def acquire(self):
        self.attempts += 1
        if self.remaining > 0:
            self.remaining -= 1
            raise RuntimeError("the pool is gone")
        return self._real.acquire()


async def test_a_worker_survives_a_failure_taking_work_and_carries_on(pool, monkeypatch) -> None:
    """The forty-minute evening, in the shape that caused it: one failure between chunks
    used to mean nothing was ever collected again until somebody restarted the module."""
    monkeypatch.setattr("market_data.jobs.runner.FAILURE_BACKOFF_SECONDS", 0.01)
    await _tracked(pool)
    async with pool.acquire() as conn:
        job = await create_job(
            conn, NOW, [plan(chunk_start=NOW - timedelta(hours=1), chunk_end=NOW)]
        )

    flaky = _FlakyPool(pool, failures=1)
    runner = JobRunner(flaky, FakeHistory([minute_candle(1)]), limiter=asyncio.Semaphore(1))
    await runner.start()
    try:
        await asyncio.sleep(0.2)
        async with pool.acquire() as conn:
            reread = await read_job(conn, job.id)
    finally:
        await runner.stop()

    assert reread.chunks[0].state is ChunkState.DONE
    assert flaky.attempts > 1  # it came back for the work by itself


async def test_a_worker_failing_to_take_work_waits_longer_each_time(
    pool, caplog, monkeypatch
) -> None:
    """A database out for an hour must not cost 720 identical log lines and 720
    connection attempts — the wait grows, up to a ceiling."""
    monkeypatch.setattr("market_data.jobs.runner.FAILURE_BACKOFF_SECONDS", 0.01)
    monkeypatch.setattr("market_data.jobs.runner.MAX_FAILURE_BACKOFF_SECONDS", 0.04)

    flaky = _FlakyPool(pool, failures=1000)
    runner = JobRunner(flaky, FakeHistory([]), limiter=asyncio.Semaphore(1))

    with caplog.at_level(logging.ERROR, logger="market_data.jobs.runner"):
        await runner.start()
        try:
            await asyncio.sleep(0.25)
        finally:
            await runner.stop()

    # Spinning would be thousands of attempts in a quarter of a second.
    assert 2 <= flaky.attempts <= 30
    assert "could not take work" in caplog.text
    assert "the pool is gone" in caplog.text
    # And the wait grows rather than staying where it started.
    assert "trying again in 0.01s" in caplog.text
    assert "trying again in 0.02s" in caplog.text
    assert "trying again in 0.08s" not in caplog.text  # capped at 0.04


async def test_a_worker_stopped_while_waiting_out_a_failure_ends_quietly(pool, caplog) -> None:
    """`stop()` is the one thing that MUST end the loop, including mid-backoff — and an
    orderly shutdown is not an incident."""
    flaky = _FlakyPool(pool, failures=1000)
    runner = JobRunner(flaky, FakeHistory([]), limiter=asyncio.Semaphore(1))
    await runner.start()
    await asyncio.sleep(0.02)  # long enough to fail once and settle into the wait

    with caplog.at_level(logging.ERROR, logger="market_data.jobs.runner"):
        await runner.stop()
        for _ in range(3):
            await asyncio.sleep(0)

    assert "died" not in caplog.text
    assert "returned" not in caplog.text
    assert all(worker.done() for worker in runner._workers) or runner._workers == []


# --- a worker that dies must say so ---------------------------------------------------


async def test_a_worker_that_dies_says_so(caplog) -> None:
    """The loop now catches everything it can reach, so this should never fire — which
    is exactly why it stays.

    A task that raises while still referenced never reports the exception — Python logs
    it on garbage collection, and `JobRunner._workers` is the reference that prevents
    that. Found the hard way: eight chunks pending in production across a restart and a
    retry, with no log line and no exception anywhere to read. An end nobody planned for
    is the end of every job this module would run, and it must not be silent.
    """

    async def dies() -> None:
        raise RuntimeError("something outside the loop's reach")

    worker = asyncio.create_task(dies(), name="job-runner-0")
    worker.add_done_callback(_report_worker_death)

    with caplog.at_level(logging.ERROR, logger="market_data.jobs.runner"):
        with pytest.raises(RuntimeError):
            await worker
        for _ in range(3):
            await asyncio.sleep(0)

    assert "died" in caplog.text
    assert "no job will run" in caplog.text
    assert "something outside the loop's reach" in caplog.text


async def test_a_worker_cancelled_on_shutdown_says_nothing(caplog) -> None:
    """`stop()` is the normal way this ends, and an orderly shutdown is not an incident."""
    runner = JobRunner(_IdlePool(), history=None, limiter=asyncio.Semaphore(1))
    await runner.start()

    with caplog.at_level(logging.ERROR, logger="market_data.jobs.runner"):
        await runner.stop()
        for _ in range(3):
            await asyncio.sleep(0)

    assert caplog.text == ""


class _IdlePool:
    """A pool whose connections find no work — the runner's idle path."""

    def acquire(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def fetchrow(self, *args):
        return None
