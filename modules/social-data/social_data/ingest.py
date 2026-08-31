"""How posts get into the archive: one pass per interval, per source, over a window.

Two things here are decisions rather than mechanics. The pass asks its source for **every UTC date
the window touches**, because the feed is addressed by date and a post published at 23:50 would
otherwise be lost every night. And the archive **does not reach backwards**: what it holds starts on
the day it was deployed, which `collecting_since` records, so an operator can tell an archive that
begins at a known moment from one that begins wherever the first pass happened to reach."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from . import store
from .models import RawPost
from .providers import PostSource, SourceError

log = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(UTC)


def dates_touched(start: datetime, end: datetime) -> list[date]:
    """Every UTC calendar date the window covers, in order. One date for the usual window, two for
    one that crosses midnight — which is every window for a fifth of the day."""
    first, last = start.astimezone(UTC).date(), end.astimezone(UTC).date()
    return [first + timedelta(days=offset) for offset in range((last - first).days + 1)]


@dataclass(frozen=True, slots=True)
class Collected:
    """What one pass over one source did. `failure` is a reason rather than a flag, because it is
    what `/state` shows and what a screen turns into a sentence."""

    source: str
    fetched: int
    inserted: int
    failure: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.failure is None


class Ingest:
    """The collection loop. Enrichment runs after it in the same pass — see `enrichment.py`."""

    def __init__(
        self,
        pool,
        sources: Sequence[PostSource],
        *,
        interval_seconds: int,
        window_hours: int,
        enrich: Callable[[datetime], object] | None = None,
        announce: Callable[[datetime], object] | None = None,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        self._pool = pool
        self._sources = tuple(sources)
        self._interval = interval_seconds
        self._window = timedelta(hours=window_hours)
        self._enrich = enrich
        self._announce = announce
        self._clock = clock
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        # Every source gets its state row before the first pass, so `/state` answers with a
        # `collecting_since` from the moment the module started rather than from its first success.
        async with self._pool.acquire() as conn:
            for source in self._sources:
                await store.begin_collecting(conn, source.name)
        self._task = asyncio.create_task(self._run(), name="social-collector")

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
                # One bad round is not the end of collection.
                log.exception("a collection round failed")
            await asyncio.sleep(self._interval)

    async def tick(self) -> list[Collected]:
        """One pass over every source, then the enrichment and the alerts this module is configured
        for — in that order, because a post is only worth announcing once a model has read it."""
        results = [await self.collect(source) for source in self._sources]
        since = self._clock() - self._window
        if self._enrich is not None:
            try:
                await self._enrich(since)  # type: ignore[misc]
            except asyncio.CancelledError:
                raise
            except Exception:
                # A model that will not answer costs the readings, never the collection: the posts
                # are already stored, and the next pass picks up whatever stayed unread.
                log.exception("enrichment failed for this round")
        if self._announce is not None:
            try:
                await self._announce(since)  # type: ignore[misc]
            except asyncio.CancelledError:
                raise
            except Exception:
                # And a gateway that will not answer costs the notification only. No marker was
                # written, so the next round offers the same posts again.
                log.exception("announcing failed for this round")
        return results

    async def collect(self, source: PostSource) -> Collected:
        """One source, one window. A source that does not answer leaves the archive and the moment of
        the last successful collection exactly as they were."""
        end = self._clock()
        start = end - self._window

        fetched: dict[str, RawPost] = {}
        failure: str | None = None
        for day in dates_touched(start, end):
            try:
                for post in await source.fetch(day):
                    fetched.setdefault(post.external_id, post)
            except SourceError as err:
                # The whole pass is a failure, not this date alone: a window is only collected if
                # every date it touches was answered, and half a window silently written is worse.
                failure = str(err)
                log.warning("source %s did not answer for %s: %s", source.name, day, err)
                break

        in_window = [post for post in fetched.values() if start <= post.published_at <= end]

        async with self._pool.acquire() as conn:
            if failure is None:
                inserted = await store.insert_new_posts(conn, in_window)
                await store.record_collection_success(conn, source.name, at=end)
            else:
                # Nothing written, not even the dates that answered before the one that did not: a
                # window is collected whole or not at all, and a half-written one is indistinguishable
                # afterwards from a quiet stretch. The next pass asks for the same window again.
                inserted = 0
                await store.record_collection_failure(conn, source.name, at=end, reason=failure)

        log.info(
            "source %s: %d posts in the window, %d new%s",
            source.name,
            len(in_window),
            inserted,
            "" if failure is None else f" (pass failed: {failure})",
        )
        return Collected(
            source=source.name, fetched=len(in_window), inserted=inserted, failure=failure
        )
