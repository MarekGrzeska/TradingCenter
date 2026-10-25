"""The run queue: runs taken oldest first, each read from the archive here and computed in a process of its own, which is
stopped — not left to finish — when it runs out of time or is cancelled. One process per run rather than a pool, because
only a process can be stopped; a pool's worker keeps computing after its caller has given up."""

from __future__ import annotations

import asyncio
import logging
import multiprocessing
import time
from collections.abc import Callable
from multiprocessing.connection import Connection
from typing import Any

import asyncpg

from . import documents, runs, store
from .archive import Archive, ArchiveUnavailable
from .config import Settings
from .costs import CostModel
from .document import execution
from .engine import ENGINE_VERSION
from .reading import bars_without_minutes, read
from .series import epoch
from .worker import Job
from .worker import main as compute_in_process

log = logging.getLogger(__name__)

# How often a running run looks at whether it was cancelled, and how long the queue sleeps when nothing woke it.
CANCEL_POLL_SECONDS = 1.0
IDLE_SECONDS = 30.0
# Spawned, not forked: this process runs an event loop and threads, and a fork copies them half-way.
_CONTEXT = multiprocessing.get_context("spawn")


class RunQueue:
    def __init__(
        self, pool: asyncpg.Pool, archive: Archive, settings: Settings,
        target: Callable[[Job, Connection], None] = compute_in_process,
    ) -> None:
        self._pool = pool
        self._archive = archive
        self._settings = settings
        self._target = target
        self._wake = asyncio.Event()
        self._loop: asyncio.Task | None = None
        self._running: set[asyncio.Task] = set()
        # Runs someone in this process is waiting on — the conversation's `run_backtest` — and the event that ends it.
        self._waiting: dict[int, asyncio.Event] = {}

    async def start(self) -> None:
        async with self._pool.acquire() as conn:
            interrupted = await runs.interrupted_by_restart(conn)
        if interrupted:
            log.warning("%d run(s) were computing when the process stopped; marked as interrupted", interrupted)
        self._loop = asyncio.create_task(self._serve(), name="strategies-run-queue")

    async def stop(self) -> None:
        if self._loop is not None:
            self._loop.cancel()
        for task in list(self._running):
            task.cancel()
        await asyncio.gather(*(t for t in [self._loop, *self._running] if t is not None), return_exceptions=True)

    def wake(self) -> None:
        self._wake.set()

    async def wait_for(self, run_id: int, timeout: float) -> None:
        """Returns when the run has ended here, or after `timeout`, whichever is first — what it ended as is the
        database's to say. `listen` first, before the queue is woken, or a fast run can end before anyone listens."""
        event = self._waiting.setdefault(run_id, asyncio.Event())
        try:
            await asyncio.wait_for(event.wait(), timeout)
        except TimeoutError:
            pass
        finally:
            self._waiting.pop(run_id, None)

    def listen(self, run_id: int) -> None:
        """Starts listening for a run's end before the queue is woken; `wait_for` then waits on the same event."""
        self._waiting.setdefault(run_id, asyncio.Event())

    @property
    def busy(self) -> int:
        return len(self._running)

    async def _serve(self) -> None:
        while True:
            while len(self._running) < self._settings.run_concurrency:
                try:
                    async with self._pool.acquire() as conn:
                        row = await runs.claim(conn)
                except Exception:
                    log.exception("the run queue could not claim a run; it tries again at the next wake")
                    break
                if row is None:
                    break
                task = asyncio.create_task(self._run(row), name=f"strategies-run-{row['id']}")
                self._running.add(task)
                task.add_done_callback(self._finished)
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=IDLE_SECONDS)
            except TimeoutError:
                pass
            self._wake.clear()

    def _finished(self, task: asyncio.Task) -> None:
        self._running.discard(task)
        self._wake.set()

    async def _run(self, row: asyncpg.Record) -> None:
        run_id = row["id"]
        try:
            await self._run_unguarded(row)
        except Exception as err:
            # A run that fails says why, and the queue keeps serving the next one.
            log.exception("run %s failed", run_id)
            try:
                async with self._pool.acquire() as conn:
                    await runs.fail(conn, run_id, f"{type(err).__name__}: {err}")
            except Exception:
                log.exception("run %s could not even be marked failed; the next start marks it interrupted", run_id)
        finally:
            listener = self._waiting.get(run_id)
            if listener is not None:
                listener.set()

    async def _run_unguarded(self, row: asyncpg.Record) -> None:
        run_id = row["id"]
        deadline = time.monotonic() + self._settings.run_timeout_seconds
        try:
            job, provenance = await asyncio.wait_for(self._prepare(row), timeout=self._settings.run_timeout_seconds)
            # Read, but cancelled meanwhile: no process is started for a run nobody wants any more.
            await self._still_wanted(run_id)
            outcome = await self._compute(run_id, job, deadline)
        except _Ends as ended:
            async with self._pool.acquire() as conn:
                await runs.fail(conn, run_id, ended.reason, ended.status)
            return
        except TimeoutError:
            async with self._pool.acquire() as conn:
                await runs.fail(conn, run_id, f"stopped after {self._settings.run_timeout_seconds:g} s, its time limit")
            return
        except ArchiveUnavailable as err:
            async with self._pool.acquire() as conn:
                await runs.fail(conn, run_id, f"the archive could not be read: {err}")
            return
        provenance["engine_version"] = outcome["engine_version"]
        await runs.finish(
            self._pool, run_id, outcome["engine_version"], outcome["report"], provenance, outcome["trades"]
        )

    async def _still_wanted(self, run_id: int) -> None:
        async with self._pool.acquire() as conn:
            # A deleted run is as unwanted as a cancelled one: its row is gone, and so is anything its result would say.
            if await runs.status_of(conn, run_id) in ("cancelled", None):
                raise _Ends("cancelled by the operator", status="cancelled")

    async def _prepare(self, row: asyncpg.Record) -> tuple[Job, dict[str, Any]]:
        request = store.decoded(row["request"])
        async with self._pool.acquire() as conn:
            revision = await store.get_revision(conn, row["strategy_id"], row["revision"])
        # Checked again against the archive as it is now: a pair untracked since the save would otherwise read as
        # a quiet market rather than as a strategy that can no longer run.
        checked, problems = await documents.check(revision.document, self._archive)
        if checked is None:
            listed = "; ".join(f"{p.path}: {p.message}" for p in problems[:3])
            raise _Ends(f"the revision no longer passes its checks: {listed}")
        catalogue, _ = await self._archive.check_inputs()
        params = request["params"]
        start, end = epoch(request["from"]), epoch(request["to"])
        inputs = await read(self._archive, checked, params, catalogue, start, end)
        d = checked.document
        settled_on = execution(d)
        if settled_on == "MINUTE":
            decision, minute = inputs.series[(d.symbol, d.timeframe)], inputs.series[(d.symbol, "MINUTE")]
            hole = bars_without_minutes(decision, minute, start, end)
            if hole is not None:
                raise _Ends(hole)
        costs = CostModel.model_validate(request["costs"])
        job = Job(
            checked, params, catalogue, inputs.series, inputs.indicators, costs, float(request["capital"]),
            start, end, int(request["seed"]), self._settings.random_entry_repetitions, request.get("margin_factor"),
        )
        provenance = {
            "strategy_id": row["strategy_id"],
            "revision": row["revision"],
            "content_hash": revision.content_hash,
            "params": params,
            "costs": request["costs"],
            "margin_factor": request.get("margin_factor"),
            "range": {"from": request["from"], "to": request["to"]},
            "capital": request["capital"],
            "seed": request["seed"],
            "engine_version": ENGINE_VERSION,
            "execution": settled_on,
            "warmup_seconds": inputs.needs.warmup_seconds,
            "read_from": inputs.read_from,
            "series": inputs.fingerprints(),
            "uncovered": {f"{s}@{r}": gaps for (s, r), gaps in sorted(inputs.uncovered.items()) if gaps},
            "unsettled": [f"{k.id}{dict(k.params)}.{k.line} @ {k.context[0]}@{k.context[1]}" for k in inputs.unsettled],
        }
        return job, provenance

    async def _compute(self, run_id: int, job: Job, deadline: float) -> dict[str, Any]:
        receiver, sender = _CONTEXT.Pipe(duplex=False)
        process = _CONTEXT.Process(target=self._target, args=(job, sender), daemon=True)
        # Off the loop: a spawned start pickles the whole job into the child's pipe and waits for it to be read.
        await asyncio.to_thread(process.start)
        sender.close()
        outcome: dict[str, Any] | None = None
        try:
            last_look = time.monotonic()
            while True:
                if receiver.poll():
                    kind, payload = receiver.recv()
                    if kind == "failed":
                        raise _Ends(payload)
                    if kind == "result":
                        outcome = payload
                        continue
                    if outcome is None:
                        raise _Ends("the worker sent a benchmark before its result")
                    outcome["report"]["benchmarks"]["random_entry"] = payload
                    return outcome
                if not process.is_alive() and not receiver.poll():
                    raise _Ends(f"the worker process ended without an answer (exit code {process.exitcode})")
                now = time.monotonic()
                if now >= deadline:
                    if outcome is not None:
                        # The run's own result is in; only the benchmark ran out of time, and says so.
                        outcome["report"]["benchmarks"]["random_entry"] = {"skipped": "the run's time limit came first"}
                        return outcome
                    raise TimeoutError
                if now - last_look >= CANCEL_POLL_SECONDS:
                    last_look = now
                    await self._still_wanted(run_id)
                await asyncio.sleep(0.05)
        finally:
            if process.is_alive():
                process.terminate()
            await asyncio.to_thread(process.join, 5)
            receiver.close()


class _Ends(Exception):
    def __init__(self, reason: str, status: str = "failed") -> None:
        self.reason = reason
        self.status = status
