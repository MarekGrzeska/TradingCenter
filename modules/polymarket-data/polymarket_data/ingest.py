"""How prices get into the archive: a tick, a backfill, and the gap a restart leaves.

The tick is one request **per event**, not two per market, and that is the whole difference
from the application this module replaces. Measured 22 August 2026: the metadata surface's
`outcomePrices` is the order book's midpoint, to the digit, for every outcome of every market
at once. A 128-market event costs one request here and 256 there.

The same request also carries the event's structure, so a market the provider adds and a
market it resolves are noticed by the tick rather than by a second loop with a second budget.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from . import parsing, provider, store
from .models import Sample, Surface

log = logging.getLogger(__name__)

# How far a returned point may sit outside a window's own edge and still be written. The
# provider's spacing wobbles between 57 and 63 seconds, so an exact edge would drop the point
# that lands on it; anything beyond this is the response overrunning the window, which it
# does routinely because `endTs` is not honoured.
EDGE_SLACK = timedelta(seconds=90)

# How much older than the window's start the oldest returned point has to be before this
# module concludes the provider has nothing older. Half a day: less than that is the series
# simply not having a point in the first minutes, which is ordinary.
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
    ) -> None:
        self._pool = pool
        self._client = client
        self._interval = interval_seconds
        self._window = timedelta(days=window_days)
        self._default_depth = timedelta(days=default_backfill_days)
        self._task: asyncio.Task | None = None
        # Backfills started by tracking, held so they are cancelled with the module rather
        # than left writing into a closing pool.
        self._backfills: set[asyncio.Task] = set()
        self.started_at: datetime | None = None

    # --- the loop --------------------------------------------------------------------

    async def start(self) -> None:
        self.started_at = _now()
        self._task = asyncio.create_task(self._run(), name="polymarket-sampler")

    def event_tracked(self, event_id: int) -> None:
        """Start filling an event's past, now rather than at the next restart.

        The route that brings an event under observation answers "the recent past is being
        filled in", and `specs/polymarket-data-ingest` requires it to start on tracking.
        Until this existed nothing called `backfill_event` outside its tests: sampling began
        immediately and the ninety days arrived only when the process next restarted and
        `close_gaps` happened to reach it.

        Fire-and-forget on purpose — the operator's request should not wait on six requests
        per outcome — but held in a set, because a bare `create_task` may be collected
        mid-flight.
        """
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
        # The gap is closed **beside** the tick, not before it. Every stop leaves a period
        # with no samples, and on this provider that period is not recoverable later — of
        # five recently resolved markets, four returned no history at all — so closing it is
        # a task rather than a nicety. But it is sequential per outcome and per window, so
        # awaiting it first meant a restart with a full watch list collected nothing live
        # for as long as the catch-up took: the spec's "uzupełnianie MUST NOT zagłodzić
        # bieżącego próbkowania", broken by the one line that ordered them.
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

    # --- one round -------------------------------------------------------------------

    async def tick(self) -> int:
        """One pass over every event still worth asking about. Returns samples written."""
        async with self._pool.acquire() as conn:
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

        async with self._pool.acquire() as conn:
            # The structure first: the same payload says whether a market has been added or
            # answered, and refreshing before writing means a new market's prices land on an
            # outcome that exists rather than being dropped.
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
            # A tick is also a collected window — **the interval it stands for, not the
            # instant it happened at.** Recorded as a point, two consecutive ticks never
            # touched, so nothing ever merged: the table grew a row per outcome per minute,
            # and `is_collected` answered false for the 59 seconds between them. Backdating
            # the start by one interval makes each tick adjacent to the last, which is what
            # `record_collected`'s merge is written for.
            covered_from = observed_at - timedelta(seconds=self._interval)
            for sample in samples:
                await store.record_collected(
                    conn, sample.outcome_id, covered_from, observed_at
                )
            await store.note_sampled(conn, event_id)
        return written

    async def _note_failure(self, event_id: int, reason: str) -> None:
        log.warning("sampling event %s failed: %s", event_id, reason)
        async with self._pool.acquire() as conn:
            await store.note_sampling_failed(conn, event_id, reason)

    # --- reaching backwards ------------------------------------------------------------

    async def backfill_event(self, event_id: int, *, since: datetime | None = None) -> int:
        """Fills an event's past, window by window. Returns samples written.

        Each window succeeds, fails and is retried on its own. A window that failed is not
        recorded as collected — otherwise the gap it left would read as "nothing traded
        then" for ever, and nothing would come back to it.
        """
        async with self._pool.acquire() as conn:
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
        # The boundary the provider taught us: nothing older than this exists, so asking for
        # it again is a request that can only come back empty. The condition was inverted —
        # `since >= oldest` then `max(since, oldest)` is `since`, a guaranteed no-op — so the
        # boundary limited nothing and every restart re-requested the same known-empty
        # windows.
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
            # No boundary is written from an empty answer. Writing one here would record
            # "the provider has nothing older" from a response that said nothing at all, and
            # this module would then never ask again.
            return 0

        # Both edges are checked here rather than trusted to the request. `endTs` is not
        # honoured by the provider — measured — so a response routinely runs to the present
        # moment whatever window was asked for, and a point written outside the window makes
        # "collected" a wider claim than what was verified.
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
        async with self._pool.acquire() as conn:
            written = await store.record_samples(conn, samples)
            await store.record_collected(conn, outcome_id, window_start, window_end)
            if oldest_returned - window_start > NOTHING_OLDER_SLACK:
                # Written at the oldest point the read actually returned, never at the edge
                # of the window asked for: those two are separated by everything the
                # provider did not have.
                await store.note_oldest_available(conn, outcome_id, oldest_returned)
        return written

    async def close_gaps(self) -> int:
        """Fills the period between each outcome's newest sample and now.

        Every stop leaves one, and on this provider it does not stay fillable: history for a
        resolved market is often simply gone. An outcome with no sample at all is backfilled
        to the configured depth instead.
        """
        async with self._pool.acquire() as conn:
            events = await store.sampleable_events(conn)

        filled = 0
        for event_id, _ in events:
            async with self._pool.acquire() as conn:
                outcomes = await store.outcomes_of_event(conn, event_id)
                newest = {
                    outcome_id: await store.newest_sample_at(conn, outcome_id)
                    for outcome_id, _, _ in outcomes
                }
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
