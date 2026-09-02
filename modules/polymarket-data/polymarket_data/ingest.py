"""How prices get into the archive: a tick, a backfill, and the gap a restart leaves. The tick is one request *per
event* — measured, the metadata surface's `outcomePrices` is the order book's midpoint to the digit."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from tc_runtime.liveness import LoopHeartbeat

from . import parsing, provider, store
from .models import Sample, Surface

log = logging.getLogger(__name__)

# How far a returned point may sit outside a window's own edge and still be written. The provider's
# spacing wobbles, and anything beyond this is the response overrunning `endTs`, which it ignores.
EDGE_SLACK = timedelta(seconds=90)

# How much older than the window's start the oldest returned point must be before this module
# concludes the provider has nothing older. Half a day: less is an ordinary thin first minute.
NOTHING_OLDER_SLACK = timedelta(hours=12)


def _now() -> datetime:
    return datetime.now(UTC)


class Ingest:
    """The sampler and the backfill, sharing the provider budget the client holds."""

    def __init__(
        self,
        pool,
        client: provider.PolymarketClient,
        *,
        interval_seconds: int,
        window_days: int,
        default_backfill_days: int,
        db_concurrency: int,
        heartbeat: LoopHeartbeat | None = None,
    ) -> None:
        self._pool = pool
        self._client = client
        # `None` in a test that drives `tick()` itself: what the loop reports is the loop's, and a
        # caller with no loop has nothing to report.
        self._heartbeat = heartbeat
        self._interval = interval_seconds
        self._window = timedelta(days=window_days)
        self._default_depth = timedelta(days=default_backfill_days)
        self._connections = asyncio.Semaphore(db_concurrency)
        self._task: asyncio.Task | None = None
        # Backfills started by tracking, held so they are cancelled with the module rather
        # than left writing into a closing pool.
        self._backfills: set[asyncio.Task] = set()
        self.started_at: datetime | None = None

    @asynccontextmanager
    async def _connection(self) -> AsyncIterator:
        """A pooled connection, and never more of them at once than collection's share of the pool.

        `tick` gathers every event, so without this the sampler held every connection there was and a
        read waited on `pool.acquire()`, which has no deadline — the screen that never finished loading.
        """
        async with self._connections, self._pool.acquire() as conn:
            yield conn

    async def start(self) -> None:
        self.started_at = _now()
        self._task = asyncio.create_task(self._run(), name="polymarket-sampler")

    def event_tracked(self, event_id: int) -> None:
        """Start filling an event's past, now rather than at the next restart. Fire-and-forget, but held
        in a set: a bare `create_task` may be collected mid-flight."""
        task = asyncio.create_task(
            self._backfill_quietly(event_id), name=f"polymarket-backfill-{event_id}"
        )
        self._backfills.add(task)
        task.add_done_callback(self._backfills.discard)

    async def _backfill_quietly(self, event_id: int) -> None:
        try:
            await self.backfill_event(event_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            # The observation stands and the tick collects from now; the past is retried by
            # `close_gaps` on the next start.
            log.exception("could not fill the past of event %s", event_id)

    async def stop(self) -> None:
        for task in list(self._backfills):
            task.cancel()
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _run(self) -> None:
        # The gap is closed *beside* the tick, not before it: it is sequential per outcome and per
        # window, so awaiting it first meant a restart collected nothing live until the catch-up ended.
        catch_up = asyncio.create_task(self._close_gaps_quietly(), name="polymarket-catch-up")
        self._backfills.add(catch_up)
        catch_up.add_done_callback(self._backfills.discard)

        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                # One bad round is not the end of collection.
                log.exception("a sampling round failed")
            else:
                # After the pass and only after it: a round that raised is a round that did not
                # happen, and a heartbeat beaten regardless would report a stopped loop as healthy.
                if self._heartbeat is not None:
                    self._heartbeat.beat()
            await asyncio.sleep(self._interval)

    async def _close_gaps_quietly(self) -> None:
        try:
            await self.close_gaps()
        except asyncio.CancelledError:
            raise
        except Exception:
            # A failed catch-up must not stop the tick: yesterday's gap is already lost, and
            # refusing to collect today would lose today's too.
            log.exception("could not close the gap left by the last stop")

    async def tick(self) -> int:
        """One pass over every event still worth asking about. Returns samples written."""
        async with self._connection() as conn:
            events = await store.sampleable_events(conn)
        if not events:
            return 0

        written = await asyncio.gather(
            *(self._sample_event(event_id, provider_id) for event_id, provider_id in events)
        )
        return sum(written)

    async def _sample_event(self, event_id: int, provider_event_id: str) -> int:
        try:
            payload = await self._client.event_payload(provider_event_id)
        except provider.ProviderHasNothing:
            # An answer, not a failure: the provider no longer has this event. Recorded as
            # the reason collection stopped rather than retried every minute for ever.
            await self._note_failure(event_id, "the provider no longer has this event")
            return 0
        except (provider.ProviderRefused, provider.ProviderUnusable) as err:
            await self._note_failure(event_id, str(err))
            return 0

        observed_at = _now()
        prices = parsing.prices_from(payload)

        async with self._connection() as conn:
            # The structure first: the same payload says whether a market has been added or answered,
            # so refreshing before writing lands a new market's prices on an outcome that exists.
            try:
                await store.upsert_event(conn, parsing.event_from(payload))
            except parsing.ProviderPayloadUnusable as err:
                await store.note_sampling_failed(conn, event_id, str(err))
                return 0

            tokens = await store.outcome_ids_by_token(conn, event_id)
            samples = [
                Sample(
                    outcome_id=tokens[token],
                    observed_at=observed_at,
                    midpoint=midpoint,
                    last_trade=last_trade,
                    source=Surface.GAMMA,
                )
                for token, (midpoint, last_trade) in prices.items()
                if token in tokens and (midpoint is not None or last_trade is not None)
            ]
            written = await store.record_samples(conn, samples)
            # A tick is also a collected window — the interval it stands for, not the instant it
            # happened at. Recorded as a point, two ticks never touched and nothing ever merged.
            covered_from = observed_at - timedelta(seconds=self._interval)
            await store.record_collected_many(
                conn, [sample.outcome_id for sample in samples], covered_from, observed_at
            )
            await store.note_sampled(conn, event_id)
        return written

    async def _note_failure(self, event_id: int, reason: str) -> None:
        log.warning("sampling event %s failed: %s", event_id, reason)
        async with self._connection() as conn:
            await store.note_sampling_failed(conn, event_id, reason)

    async def backfill_event(self, event_id: int, *, since: datetime | None = None) -> int:
        """Fills an event's past, window by window. Each window succeeds, fails and is retried on its
        own: a failed window is not recorded as collected, or its gap would read as "nothing traded"."""
        async with self._connection() as conn:
            outcomes = await store.outcomes_of_event(conn, event_id)
        if not outcomes:
            return 0

        start = since or (_now() - self._default_depth)
        written = await asyncio.gather(
            *(
                self._backfill_outcome(outcome_id, token_id, start, oldest)
                for outcome_id, token_id, oldest in outcomes
            )
        )
        return sum(written)

    async def _backfill_outcome(
        self, outcome_id: int, token_id: str, since: datetime, oldest_available: datetime | None
    ) -> int:
        # The boundary the provider taught us. The condition was inverted, so the boundary limited
        # nothing and every restart re-requested the same known-empty windows.
        if oldest_available is not None and since < oldest_available:
            since = oldest_available

        written = 0
        window_start = since
        now = _now()
        while window_start < now:
            window_end = min(window_start + self._window, now)
            try:
                written += await self._fill_window(outcome_id, token_id, window_start, window_end)
            except provider.ProviderError as err:
                # This window only. The rest of the range is still worth having, and this one
                # stays uncollected so a later run comes back to it.
                log.warning(
                    "backfill window %s..%s for outcome %s failed: %s",
                    window_start.isoformat(),
                    window_end.isoformat(),
                    outcome_id,
                    err,
                )
            window_start = window_end
        return written

    async def _fill_window(
        self, outcome_id: int, token_id: str, window_start: datetime, window_end: datetime
    ) -> int:
        points = await self._client.price_history(
            token_id, since=window_start, until=window_end
        )
        if not points:
            # No boundary is written from an empty answer: that would record "the provider has
            # nothing older" from a response that said nothing at all, and it would never ask again.
            return 0

        # Both edges are checked here rather than trusted to the request: `endTs` is not honoured, so
        # a response routinely runs to the present, and a point outside the window widens the claim.
        low = window_start - EDGE_SLACK
        high = window_end + EDGE_SLACK
        inside = [
            (moment, price)
            for moment, price in points
            if low <= datetime.fromtimestamp(moment, UTC) <= high
        ]
        if not inside:
            return 0

        samples = [
            Sample(
                outcome_id=outcome_id,
                observed_at=datetime.fromtimestamp(moment, UTC),
                midpoint=price,
                source=Surface.CLOB,
            )
            for moment, price in inside
        ]

        oldest_returned = datetime.fromtimestamp(points[0][0], UTC)
        async with self._connection() as conn:
            written = await store.record_samples(conn, samples)
            await store.record_collected(conn, outcome_id, window_start, window_end)
            if oldest_returned - window_start > NOTHING_OLDER_SLACK:
                # Written at the oldest point the read actually returned, never at the edge of the
                # window asked for: those two are separated by everything the provider did not have.
                await store.note_oldest_available(conn, outcome_id, oldest_returned)
        return written

    async def close_gaps(self) -> int:
        """Fills the period between each outcome's newest sample and now. Every stop leaves one, and on
        this provider it does not stay fillable — history for a resolved market is often simply gone."""
        async with self._connection() as conn:
            events = await store.sampleable_events(conn)

        filled = 0
        for event_id, _ in events:
            async with self._connection() as conn:
                outcomes = await store.outcomes_of_event(conn, event_id)
                newest = await store.newest_sample_at(conn, event_id)
            now = _now()
            for outcome_id, token_id, oldest in outcomes:
                last = newest.get(outcome_id)
                since = last if last is not None else now - self._default_depth
                if last is not None and now - last < timedelta(seconds=self._interval):
                    # Current. A module that stopped and started inside one tick has no gap,
                    # and asking anyway would spend the budget proving it.
                    continue
                filled += await self._backfill_outcome(outcome_id, token_id, since, oldest)
        return filled
