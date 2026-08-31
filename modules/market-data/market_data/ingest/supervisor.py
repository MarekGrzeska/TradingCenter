"""Ingest for every tracked pair, and the one budget they all spend from. One object rather than a
task per pair, because the provider's ten requests a second are counted against the account."""

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


# How long a pair waits before being started again after its task died. Longer than a feed
# reconnect: this path is for a failure that got past `run()`'s own guard.
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
        # One semaphore for the whole process. A per-pair budget is no budget: twenty pairs would
        # each politely run one fill and together spend twenty times the allowance.
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
        """Begin collecting every pair the operator has decided on. Each pair closes its own gap
        before it subscribes, which is what makes a restart catch up rather than resume with a hole."""
        # Public because "how long has ingest been up" is the first thing asked of a stale feed,
        # and it tells a process that just restarted from one failing quietly for hours.
        self.started_at = datetime.now(UTC)
        await self.sync()

    async def sync(self) -> None:
        """Match the running tasks to the tracked pairs, at start and whenever the operator changes
        the list — so adding a pair starts collecting it without a restart."""
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
        """Say that a pair stopped collecting, and start it again. Without this the end is the quietest
        thing here: on 10 August a process kept its pairs "collecting" for forty minutes after all died."""
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
            # `run()` returns when the pair stops being tracked, which `_stop_pair` would have
            # cancelled — so reaching here means it read "untracked" itself. Nothing wrong.
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
        """Start a died pair again, after a pause. The pause keeps an immediately recurring failure
        from becoming a spin, and is longer than a feed reconnect for the same reason as above."""
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
