"""Collection: one request per event, a window that clips on the way out, and a failure that
writes nothing."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import fakes
import pytest

from polymarket_data import parsing, provider, store
from polymarket_data.ingest import Ingest
from polymarket_data.models import Sample, Surface

pytestmark = pytest.mark.db


def ingest(pool, fake, **kwargs) -> Ingest:
    return Ingest(
        pool,
        fake,  # type: ignore[arg-type]
        interval_seconds=kwargs.pop("interval_seconds", 60),
        window_days=kwargs.pop("window_days", 15),
        default_backfill_days=kwargs.pop("default_backfill_days", 90),
    )


async def track(pool, payload: dict) -> int:
    async with pool.acquire() as conn:
        return await store.upsert_event(conn, parsing.event_from(payload))


class TestTheTick:
    async def test_one_request_prices_every_outcome_of_every_market(self, pool) -> None:
        """The whole difference from the application this module replaces: the metadata surface carries
        the midpoint of every outcome at once, so a 128-market event costs one request rather than 256."""
        payload = fakes.event_payload(
            markets=(
                fakes.market_payload("m-1", prices=("0.6", "0.4")),
                fakes.market_payload(
                    "m-2", outcomes=("A", "B", "C"), prices=("0.2", "0.3", "0.5"),
                    last_trade=None,
                ),
            )
        )
        await track(pool, payload)
        fake = fakes.FakeProvider({"e-1": payload})

        written = await ingest(pool, fake).tick()

        assert written == 5
        assert fake.event_calls == ["e-1"], "one request, not one per market"
        async with pool.acquire() as conn:
            latest = await store.latest_samples(conn)
        assert len(latest) == 5
        assert sorted(str(s.midpoint) for s in latest.values()) == [
            "0.200000", "0.300000", "0.400000", "0.500000", "0.600000",
        ]

    async def test_the_same_request_notices_a_market_the_provider_added(self, pool) -> None:
        first = fakes.event_payload(markets=(fakes.market_payload("m-1"),))
        await track(pool, first)
        grown = fakes.event_payload(
            markets=(fakes.market_payload("m-1"), fakes.market_payload("m-2"))
        )

        await ingest(pool, fakes.FakeProvider({"e-1": grown})).tick()

        async with pool.acquire() as conn:
            [event] = await store.load_events(conn)
        assert len(event.markets) == 2

    async def test_a_resolved_market_drops_out_of_the_next_round(self, pool) -> None:
        payload = fakes.event_payload(
            markets=(
                fakes.market_payload("m-1", closed=True, prices=("1", "0"), last_trade=None),
                fakes.market_payload("m-2"),
            )
        )
        await track(pool, payload)

        await ingest(pool, fakes.FakeProvider({"e-1": payload})).tick()

        async with pool.acquire() as conn:
            outcomes = await store.outcomes_of_event(conn, (await store.load_events(conn))[0].id)
        # Only the unresolved market's two outcomes are still worth asking about.
        assert len(outcomes) == 2

    async def test_a_failed_read_writes_no_price_at_all(self, pool) -> None:
        """Not a placeholder and not the last known price repeated: a series with a repeated
        price reads like a market standing still rather than collection that failed."""
        payload = fakes.event_payload()
        event_id = await track(pool, payload)
        fake = fakes.FakeProvider({"e-1": provider.ProviderRefused("503 from the provider")})

        written = await ingest(pool, fake).tick()

        assert written == 0
        async with pool.acquire() as conn:
            assert await conn.fetchval("SELECT count(*) FROM price_samples") == 0
            state = await store.sampling_state(conn)
        assert state[event_id]["consecutive_failures"] == 1
        assert "503" in state[event_id]["last_failure_reason"]

    async def test_repeated_failure_is_visible_in_the_observation_state(self, pool) -> None:
        """A failure that lives only in a log is a failure nobody reads."""
        event_id = await track(pool, fakes.event_payload())
        fake = fakes.FakeProvider({"e-1": provider.ProviderRefused("still down")})
        sampler = ingest(pool, fake)

        await sampler.tick()
        await sampler.tick()
        await sampler.tick()

        async with pool.acquire() as conn:
            state = await store.sampling_state(conn)
        assert state[event_id]["consecutive_failures"] == 3

    async def test_a_success_clears_the_failure_count(self, pool) -> None:
        payload = fakes.event_payload()
        event_id = await track(pool, payload)
        fake = fakes.FakeProvider({"e-1": provider.ProviderRefused("down")})
        sampler = ingest(pool, fake)
        await sampler.tick()

        fake.payloads["e-1"] = payload
        await sampler.tick()

        async with pool.acquire() as conn:
            state = await store.sampling_state(conn)
        assert state[event_id]["consecutive_failures"] == 0
        assert state[event_id]["last_failure_reason"] is None

    async def test_a_removed_observation_is_not_asked_about(self, pool) -> None:
        payload = fakes.event_payload()
        await track(pool, payload)
        async with pool.acquire() as conn:
            await store.remove_event(conn, "e-1")
        fake = fakes.FakeProvider({"e-1": payload})

        assert await ingest(pool, fake).tick() == 0
        assert fake.event_calls == []


class TestATickIsAWindowNotAnInstant:
    async def test_consecutive_ticks_merge_into_one_collected_range(self, pool) -> None:
        """Recorded as an instant, two ticks a minute apart never touched, so `collected_ranges` grew a
        row per outcome per minute — some 368k a day for one 256-outcome event."""
        payload = fakes.event_payload(markets=(fakes.market_payload("m-1", prices=("0.6", "0.4")),))
        event_id = await track(pool, payload)
        fake = fakes.FakeProvider({"e-1": payload})
        sampler = ingest(pool, fake)

        await sampler.tick()
        await sampler.tick()

        async with pool.acquire() as conn:
            outcomes = await store.outcomes_of_event(conn, event_id)
            ranges = await store.collected_ranges(conn, outcomes[0][0])

        assert len(ranges) == 1, "two ticks, one range — they touch"


class TestBackfill:
    async def test_a_window_is_asked_for_in_provider_sized_pieces(self, pool) -> None:
        """Fifteen days is the provider's cap between startTs and endTs — measured, and on
        the interval rather than the point count, so a coarser resolution buys nothing."""
        event_id = await track(pool, fakes.event_payload())
        fake = fakes.FakeProvider()

        await ingest(pool, fake, window_days=15).backfill_event(
            event_id, since=_now() - timedelta(days=40)
        )

        windows = [(since, until) for _, since, until in fake.history_calls]
        for since, until in windows:
            assert until - since <= timedelta(days=15) + timedelta(seconds=1)
        # Two outcomes, three windows each over forty days.
        assert len(windows) == 6

    async def test_points_outside_the_window_are_not_written(self, pool) -> None:
        """`endTs` is not honoured by the provider, so a response routinely runs to the present. A point
        written outside the window makes "collected" a wider claim than what was verified."""
        event_id = await track(pool, fakes.event_payload())
        start = _now() - timedelta(days=2)
        end = start + timedelta(days=1)
        inside = int((start + timedelta(hours=6)).timestamp())
        overrun = int((end + timedelta(days=5)).timestamp())
        fake = fakes.FakeProvider(
            history={"m-1-t0": [(inside, "0.4"), (overrun, "0.9")], "m-1-t1": []}
        )

        await ingest(pool, fake, window_days=1).backfill_event(event_id, since=start)

        async with pool.acquire() as conn:
            outcomes = await store.outcomes_of_event(conn, event_id)
            series = await store.history(
                conn, outcomes[0][0], since=start - timedelta(days=1), until=_now()
            )
        assert [s.observed_at.timestamp() for s in series] == [float(inside)]

    async def test_an_empty_answer_records_no_boundary_and_no_collected_window(
        self, pool
    ) -> None:
        """Writing "the provider has nothing older" from a response that said nothing at all
        would stop this module ever asking again."""
        event_id = await track(pool, fakes.event_payload())
        fake = fakes.FakeProvider(history={})

        await ingest(pool, fake, window_days=15).backfill_event(
            event_id, since=_now() - timedelta(days=10)
        )

        async with pool.acquire() as conn:
            outcome_id, _, oldest = (await store.outcomes_of_event(conn, event_id))[0]
            ranges = await store.collected_ranges(conn, outcome_id)
        assert oldest is None
        assert ranges == []

    async def test_a_window_that_failed_is_not_recorded_as_collected(self, pool) -> None:
        """Otherwise the gap reads as "nothing traded then" for ever, and nothing comes
        back to it."""
        event_id = await track(pool, fakes.event_payload())
        fake = fakes.FakeProvider(
            history={"m-1-t0": provider.ProviderRefused("429"), "m-1-t1": []}
        )

        await ingest(pool, fake, window_days=15).backfill_event(
            event_id, since=_now() - timedelta(days=5)
        )

        async with pool.acquire() as conn:
            outcome_id, _, _ = (await store.outcomes_of_event(conn, event_id))[0]
            assert await store.collected_ranges(conn, outcome_id) == []

    async def test_the_oldest_boundary_is_the_oldest_point_returned(self, pool) -> None:
        """Never the edge of the window asked for: those two are separated by everything the
        provider did not have."""
        event_id = await track(pool, fakes.event_payload())
        start = _now() - timedelta(days=10)
        first_point = start + timedelta(days=4)
        fake = fakes.FakeProvider(
            history={"m-1-t0": [(int(first_point.timestamp()), "0.5")], "m-1-t1": []}
        )

        await ingest(pool, fake, window_days=15).backfill_event(event_id, since=start)

        async with pool.acquire() as conn:
            _, _, oldest = (await store.outcomes_of_event(conn, event_id))[0]
        assert oldest is not None
        assert abs((oldest - first_point).total_seconds()) < 1


class TestTheProvidersOwnBoundary:
    async def test_a_backfill_does_not_reach_before_what_the_provider_admits_to(
        self, pool
    ) -> None:
        """The clamp was inverted — a guaranteed no-op — so the boundary the provider taught us limited
        nothing and every restart re-requested the same known-empty windows."""
        payload = fakes.event_payload(markets=(fakes.market_payload("m-1", prices=("0.6", "0.4")),))
        event_id = await track(pool, payload)
        oldest = _now() - timedelta(days=3)
        async with pool.acquire() as conn:
            outcomes = await store.outcomes_of_event(conn, event_id)
            for outcome_id, _token, _oldest in outcomes:
                await store.note_oldest_available(conn, outcome_id, oldest)

        fake = fakes.FakeProvider({"e-1": payload})
        await ingest(pool, fake).backfill_event(event_id, since=_now() - timedelta(days=60))

        asked_from = [since for _token, since, _until in fake.history_calls]
        assert asked_from, "the backfill did ask for something"
        assert min(asked_from) >= oldest - timedelta(seconds=1), (
            "nothing older than the provider's own boundary was requested"
        )


class TestClosingTheGapARestartLeaves:
    async def test_the_period_since_the_newest_sample_is_asked_for(self, pool) -> None:
        """Every stop leaves one, and on this provider it does not stay fillable: four of
        five recently resolved markets returned no history at all."""
        payload = fakes.event_payload()
        event_id = await track(pool, payload)
        stale = _now() - timedelta(hours=6)
        async with pool.acquire() as conn:
            outcomes = await store.outcomes_of_event(conn, event_id)
            await store.record_samples(
                conn,
                [
                    _sample(outcome_id, stale)
                    for outcome_id, _, _ in outcomes
                ],
            )
        fake = fakes.FakeProvider({"e-1": payload})

        await ingest(pool, fake).close_gaps()

        assert fake.history_calls, "a six-hour gap must be asked about"
        for _, since, _ in fake.history_calls:
            assert abs((since - stale).total_seconds()) < 2

    async def test_a_restart_inside_one_tick_asks_for_nothing(self, pool) -> None:
        """Current is current. Asking anyway would spend the budget proving it."""
        payload = fakes.event_payload()
        event_id = await track(pool, payload)
        async with pool.acquire() as conn:
            outcomes = await store.outcomes_of_event(conn, event_id)
            await store.record_samples(
                conn, [_sample(outcome_id, _now()) for outcome_id, _, _ in outcomes]
            )
        fake = fakes.FakeProvider({"e-1": payload})

        await ingest(pool, fake, interval_seconds=60).close_gaps()

        assert fake.history_calls == []


def _now() -> datetime:
    return datetime.now(UTC)


def _sample(outcome_id: int, moment: datetime) -> Sample:
    return Sample(
        outcome_id=outcome_id,
        observed_at=moment,
        midpoint=Decimal("0.5"),
        source=Surface.GAMMA,
    )
