"""Ingest for every tracked pair, and the one budget they all spend from.

The budget is the reason this is a single object rather than a task per pair started
wherever a pair is added. Every fill goes through the gateway's shared rate gate, which
is the provider's ten requests a second counted against the account — so the limit has to
be held in one place that all of them queue behind. Two deep fills running together are
enough to starve the chart an operator is looking at right now, and that operator's reads
cross the same gate.

Adding or removing a pair takes effect without a restart: `sync` reconciles the running
tasks against what the operator has decided.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from ..gateway import GatewayHistory
from ..models import Resolution
from ..tracking import is_tracked, read_tracked
from .live import Backoff, PairIngest

log = logging.getLogger(__name__)

Pair = tuple[str, Resolution]


# How long a pair waits before being started again after its task died. Longer than a
# feed reconnect on purpose: this path is for a failure that got past `run()`'s own
# guard, which is rarer and less likely to have cleared a second later.
REVIVE_DELAY_SECONDS = 30.0


class Ingest:
    """Runs one subscription per tracked pair, under one shared fill budget."""

    def __init__(
        self,
        pool,
        history: GatewayHistory,
        stream_url: str,
        *,
        default_bars: int,
        backfill_concurrency: int = 1,
        backoff: Backoff | None = None,
        limiter: asyncio.Semaphore | None = None,
        **pair_options,
    ) -> None:
        self._pool = pool
        self._history = history
        self._stream_url = stream_url
        self._default_bars = default_bars
        # One semaphore for the whole process, not one per pair. A per-pair budget is no
        # budget at all: twenty pairs would each politely run one fill and together spend
        # twenty times the allowance.
        #
        # `limiter` lets a caller hand in a semaphore built elsewhere, so this budget can
        # be the *same* object a collection job runner draws from — one gate for every
        # gateway request this process makes on its own initiative, not two gates that
        # happen to share a number (design.md, "Zlecenia dzielą budżet ruchu z resztą
        # modułu").
        self._limiter = limiter if limiter is not None else asyncio.Semaphore(backfill_concurrency)
        self._backoff = backoff
        self._pair_options = pair_options
        self._tasks: dict[Pair, asyncio.Task] = {}
        # Held so a revival in flight is not garbage-collected mid-sleep, and so
        # `stop()` can cancel one rather than leave it starting a pair after shutdown.
        self._revivals: set[asyncio.Task] = set()
        self.started_at: datetime | None = None

    @property
    def running(self) -> set[Pair]:
        return set(self._tasks)

    async def start(self) -> None:
        """Begin collecting every pair the operator has decided on.

        Each pair closes its own gap before it subscribes, which is what makes a restart
        after an outage catch up rather than resume with a hole in the middle.
        """
        # Public because "how long has ingest been up" is the first thing asked of a feed
        # that looks stale, and the answer distinguishes a process that just restarted
        # from one that has been quietly failing for hours.
        self.started_at = datetime.now(UTC)
        await self.sync()

    async def sync(self) -> None:
        """Match the running tasks to the tracked pairs.

        Called at start and whenever the operator changes the list, so adding a pair
        starts collecting it without a restart and removing one stops within a period.
        """
        async with self._pool.acquire() as conn:
            wanted = {(pair.symbol, pair.resolution) for pair in await read_tracked(conn)}

        for pair in wanted - self.running:
            self._start_pair(*pair)

        for pair in self.running - wanted:
            await self._stop_pair(pair)

        # A task that ended on its own — cancelled, or a bug that escaped the loop — is
        # forgotten here rather than left in the map looking like it is still collecting.
        for pair, task in list(self._tasks.items()):
            if task.done():
                self._tasks.pop(pair, None)

    async def stop(self) -> None:
        """Stop everything and wait for it, so nothing writes after the process says it
        has shut down."""
        for revival in list(self._revivals):
            revival.cancel()
        self._revivals.clear()
        for pair in list(self._tasks):
            await self._stop_pair(pair)

    def _start_pair(self, symbol: str, resolution: Resolution) -> None:
        async def still_tracked() -> bool:
            async with self._pool.acquire() as conn:
                return await is_tracked(conn, symbol, resolution)

        ingest = PairIngest(
            pool=self._pool,
            history=self._history,
            stream_url=self._stream_url,
            symbol=symbol,
            resolution=resolution,
            default_bars=self._default_bars,
            still_tracked=still_tracked,
            limiter=self._limiter,
            backoff=self._backoff or Backoff(),
            **self._pair_options,
        )
        log.info("ingest starting for %s %s", symbol, resolution.value)
        task = asyncio.create_task(ingest.run(), name=f"ingest {symbol} {resolution.value}")
        task.add_done_callback(lambda ended: self._pair_ended(symbol, resolution, ended))
        self._tasks[(symbol, resolution)] = task

    def _pair_ended(self, symbol: str, resolution: Resolution, task: asyncio.Task) -> None:
        """Say that a pair stopped collecting, and start it again.

        Without this the end is the quietest thing that happens here. `run()` returning
        or raising leaves the task in `_tasks` looking exactly like one that is working:
        `/pairs` still lists the pair, `running` still counts it, and the only symptom is
        an archive that quietly stops gaining candles. `sync()` clears the corpse, but
        `sync()` runs at start and when the operator edits the list — so on 10 August a
        process kept its pairs "collecting" for forty minutes after every one of them had
        died, and it took reading the database to notice.

        The same reasoning as `JobRunner._report_worker_death`, and the same conclusion:
        an end nobody planned for must not be silent. This one goes further and revives
        the pair, because unlike a job's worker there is nothing else to pick the work up.
        """
        if task.cancelled() or self._tasks.get((symbol, resolution)) is not task:
            return  # `_stop_pair`, or already replaced — the ordinary way this ends.

        error = task.exception()
        if error is not None:
            log.error(
                "ingest for %s %s died; restarting in %ss",
                symbol,
                resolution.value,
                REVIVE_DELAY_SECONDS,
                exc_info=error,
            )
        else:
            # `run()` returns when the pair stops being tracked, which `_stop_pair` would
            # have cancelled — so reaching here means it read "untracked" itself. Nothing
            # to revive, and nothing wrong.
            log.info("ingest for %s %s stopped: no longer tracked", symbol, resolution.value)
            self._tasks.pop((symbol, resolution), None)
            return

        self._tasks.pop((symbol, resolution), None)
        self._revivals.add(
            asyncio.create_task(
                self._revive(symbol, resolution), name=f"revive {symbol} {resolution.value}"
            )
        )

    async def _revive(self, symbol: str, resolution: Resolution) -> None:
        """Start a died pair again, after a pause.

        The pause is what keeps a failure that recurs immediately — a database that is
        down, a bug on the first line — from becoming a spin that fills the log and the
        rate budget. It is deliberately longer than a feed reconnect: this path is for
        something that got past `run()`'s own guard, which is rarer and less likely to
        clear in a second.
        """
        try:
            await asyncio.sleep(REVIVE_DELAY_SECONDS)
            async with self._pool.acquire() as conn:
                if not await is_tracked(conn, symbol, resolution):
                    return
            if (symbol, resolution) not in self._tasks:
                self._start_pair(symbol, resolution)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("could not restart ingest for %s %s", symbol, resolution.value)
        finally:
            self._revivals.discard(asyncio.current_task())  # type: ignore[arg-type]

    async def _stop_pair(self, pair: Pair) -> None:
        task = self._tasks.pop(pair, None)
        if task is None:
            return
        log.info("ingest stopping for %s %s", pair[0], pair[1].value)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            log.exception("ingest for %s %s ended badly", pair[0], pair[1].value)
