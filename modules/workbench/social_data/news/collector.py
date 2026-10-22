"""The news loop: a short tick that fetches every feed whose own interval has passed, a few at a time, and
sweeps what retention let go of once an hour.

A feed that fails is that feed's state, never the loop's: the pass completes and the heartbeat beats. Only a
pass that raised is a pass that did not happen."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta

from tc_runtime.liveness import LoopHeartbeat

from . import store
from .fetch import FeedClient, Fetched, FetchFailed
from .latency import CLOCK_TOLERANCE
from .sources import NewsSource

log = logging.getLogger(__name__)

CONCURRENCY = 4
SWEEP_EVERY = timedelta(hours=1)


def _now() -> datetime:
    return datetime.now(UTC)


class NewsCollector:
    def __init__(
        self,
        pool,
        client: FeedClient,
        sources: Sequence[NewsSource],
        *,
        tick_seconds: int,
        retention: timedelta,
        clock: Callable[[], datetime] = _now,
        heartbeat: LoopHeartbeat | None = None,
    ) -> None:
        self._pool = pool
        self._client = client
        self._sources = tuple(sources)
        self._tick = tick_seconds
        self._retention = retention
        self._clock = clock
        self._heartbeat = heartbeat
        # In memory: after a restart every feed is due at once, which is one fetch each and no harm.
        self._last_attempt: dict[str, datetime] = {}
        self._last_sweep: datetime | None = None
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        async with self._pool.acquire() as conn:
            await store.declare_sources(conn, [source.id for source in self._sources])
        self._task = asyncio.create_task(self._run(), name="news-collector")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _run(self) -> None:
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("a news pass failed")
            else:
                if self._heartbeat is not None:
                    self._heartbeat.beat()
            await asyncio.sleep(self._tick)

    def due(self, now: datetime) -> list[NewsSource]:
        return [
            source
            for source in self._sources
            if (last := self._last_attempt.get(source.id)) is None
            or now - last >= timedelta(seconds=source.interval_seconds)
        ]

    async def tick(self) -> None:
        now = self._clock()
        due = self.due(now)
        gate = asyncio.Semaphore(CONCURRENCY)

        async def one(source: NewsSource) -> None:
            async with gate:
                await self.collect(source)

        for source in due:
            self._last_attempt[source.id] = now
        await asyncio.gather(*(one(source) for source in due))

        if self._last_sweep is None or now - self._last_sweep >= SWEEP_EVERY:
            async with self._pool.acquire() as conn:
                swept = await store.sweep(conn, before=now - self._retention)
            self._last_sweep = now
            if swept:
                log.info("news retention swept %d headlines", swept)

    async def collect(self, source: NewsSource) -> None:
        try:
            fetched = await self._client.fetch(source)
        except FetchFailed as err:
            log.warning("news source %s failed: %s", source.id, err)
            async with self._pool.acquire() as conn:
                await store.record_failure(conn, source.id, at=self._clock(), reason=str(err))
            return
        await self._store(source, fetched)

    async def _store(self, source: NewsSource, fetched: Fetched) -> None:
        # The moment the answer arrived is the moment of first sight, and the measurement's upper bound.
        seen_at = self._clock()
        newest = max(
            (
                item.published_at
                for item in fetched.items
                if item.published_at is not None and item.published_at <= seen_at + CLOCK_TOLERANCE
            ),
            default=None,
        )
        async with self._pool.acquire() as conn, conn.transaction():
            previous = await store.previous_success(conn, source.id)
            inserted = await store.insert_items(
                conn, source.id, fetched.items, seen_at=seen_at, previous_fetch_at=previous
            )
            await store.record_success(conn, source.id, at=seen_at, newest_published_at=newest)
        if inserted:
            log.info("news source %s: %d new of %d", source.id, inserted, len(fetched.items))
