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
from .backfill import FillOutcome
from .live import Backoff, PairIngest

log = logging.getLogger(__name__)

Pair = tuple[str, Resolution]


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
        self._fills: dict[Pair, FillOutcome] = {}
        self.started_at: datetime | None = None

    @property
    def running(self) -> set[Pair]:
        return set(self._tasks)

    def last_fill(self, symbol: str, resolution: Resolution) -> FillOutcome | None:
        """What the most recent fill for this pair did. `None` if it has not run yet."""
        return self._fills.get((symbol, resolution))

    def fills(self) -> dict[Pair, FillOutcome]:
        return dict(self._fills)

    def report(self) -> list[str]:
        """One readable line per pair, for an operator rather than a dashboard."""
        return [outcome.describe() for outcome in self._fills.values()]

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
            on_fill=self._record_fill,
            backoff=self._backoff or Backoff(),
            **self._pair_options,
        )
        log.info("ingest starting for %s %s", symbol, resolution.value)
        self._tasks[(symbol, resolution)] = asyncio.create_task(
            ingest.run(), name=f"ingest {symbol} {resolution.value}"
        )

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

    def _record_fill(self, outcome: FillOutcome) -> None:
        self._fills[(outcome.symbol, outcome.resolution)] = outcome
