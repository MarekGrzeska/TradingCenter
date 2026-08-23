"""The archive: what it keeps, what it refuses to lose, and what it can say about gaps."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import builders
import pytest

from polymarket_data import store, tracking
from polymarket_data.models import Sample, Surface

NOON = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)


async def outcome_ids(db, event_id: int) -> list[int]:
    rows = await db.fetch(
        "SELECT o.id FROM outcomes o JOIN markets m ON m.id = o.market_id "
        "WHERE m.event_id = $1 ORDER BY m.id, o.position",
        event_id,
    )
    return [row["id"] for row in rows]


class TestStructure:
    @pytest.mark.db
    async def test_a_market_with_more_than_two_outcomes_is_kept_whole(self, db) -> None:
        """The source application stored a sample only where the outcomes were exactly Yes
        and No, and everything else vanished without a line in a log."""
        five_ways = builders.multi_outcome_market(
            "Who wins?", ("Alice", "Bob", "Carol", "Dave", "Erin")
        )
        event_id = await store.upsert_event(db, builders.event(markets=(five_ways,)))

        [loaded] = await store.load_events(db, provider_event_id=None)
        assert loaded.id == event_id
        assert [outcome.name for outcome in loaded.markets[0].outcomes] == [
            "Alice",
            "Bob",
            "Carol",
            "Dave",
            "Erin",
        ]

    @pytest.mark.db
    async def test_a_refresh_keeps_the_outcome_ids_its_history_hangs_from(self, db) -> None:
        """Replacing markets on refresh would take every outcome id with it, and
        `price_samples` cascades from those ids — a refresh would delete the history it was
        refreshing. The provider adding a market to a running event is measured, so this
        path runs often."""
        first = builders.binary_market("Will it?", provider_market_id="m-1")
        original = builders.event(markets=(first,), provider_event_id="e-1")
        event_id = await store.upsert_event(db, original)
        [yes_id, _] = await outcome_ids(db, event_id)

        await store.record_samples(
            db,
            [Sample(outcome_id=yes_id, observed_at=NOON, midpoint=Decimal("0.4"),
                    source=Surface.GAMMA)],
        )

        # The provider adds a second market to the same event.
        await store.upsert_event(
            db,
            builders.event(
                markets=(first, builders.binary_market("And also?", provider_market_id="m-2")),
                provider_event_id="e-1",
            ),
        )

        assert await db.fetchval(
            "SELECT count(*) FROM price_samples WHERE outcome_id = $1", yes_id
        ) == 1
        [loaded] = await store.load_events(db, provider_event_id="e-1")
        assert len(loaded.markets) == 2

    @pytest.mark.db
    async def test_resolution_stops_sampling_and_keeps_the_history(self, db) -> None:
        market = builders.binary_market("Will it?", provider_market_id="m-3")
        event_id = await store.upsert_event(db, builders.event(markets=(market,)))
        [yes_id, _] = await outcome_ids(db, event_id)
        await store.record_samples(
            db,
            [Sample(outcome_id=yes_id, observed_at=NOON, midpoint=Decimal("0.9"),
                    source=Surface.GAMMA)],
        )

        assert await store.mark_resolved(db, "m-3", "Yes")

        assert await store.sampleable_outcomes(db) == []
        assert await db.fetchval("SELECT count(*) FROM price_samples") == 1
        # And the event stays on the list, marked, rather than disappearing from it.
        [loaded] = await store.load_events(db)
        assert loaded.resolved


class TestRemovingAnObservation:
    """The only way an event leaves the list, and it takes everything with it.

    What used to be here was three tests about an ending that stuck — a state produced by a
    route and a tool that both existed to produce it. Neither exists now, so neither does
    the state (`openspec/changes/an-observation-is-collected-or-gone`).
    """

    @pytest.mark.db
    async def test_removal_takes_the_markets_outcomes_samples_and_ranges(self, db) -> None:
        """One statement, and the atomicity is the schema's: everything below the event
        cascades from it, so there is no order to get wrong."""
        event_id = await store.upsert_event(db, builders.event(provider_event_id="e-1"))
        [yes_id, _] = await outcome_ids(db, event_id)
        await store.record_samples(
            db,
            [Sample(outcome_id=yes_id, observed_at=NOON, midpoint=Decimal("0.4"),
                    source=Surface.GAMMA)],
        )
        await store.record_collected(db, yes_id, NOON, NOON + timedelta(hours=1))

        assert await store.remove_event(db, "e-1")

        assert await store.load_events(db) == []
        for table in ("markets", "outcomes", "price_samples", "collected_ranges"):
            assert await db.fetchval(f"SELECT count(*) FROM {table}") == 0, table

    @pytest.mark.db
    async def test_removing_something_that_is_not_observed_says_so(self, db) -> None:
        assert await store.remove_event(db, "never-tracked") is False

    @pytest.mark.db
    async def test_tracking_it_again_after_removal_starts_from_nothing(self, db) -> None:
        """The difference worth stating: ending an observation used to keep the history, so
        re-tracking continued a series. After a removal there is no series to continue."""
        event_id = await store.upsert_event(db, builders.event(provider_event_id="e-2"))
        [yes_id, _] = await outcome_ids(db, event_id)
        await store.record_samples(
            db,
            [Sample(outcome_id=yes_id, observed_at=NOON, midpoint=Decimal("0.6"),
                    source=Surface.GAMMA)],
        )
        await store.remove_event(db, "e-2")

        again = await store.upsert_event(db, builders.event(provider_event_id="e-2"))
        [fresh_yes, _] = await outcome_ids(db, again)

        assert await store.history(db, fresh_yes, since=NOON, until=NOON) == []
        assert await store.collected_ranges(db, fresh_yes) == []


class TestSamples:
    @pytest.mark.db
    async def test_the_same_moment_from_two_directions_stays_one_row(self, db) -> None:
        """The sampler and a backfill meet in the same minute regularly. Two rows for one
        moment leave a series with two prices at one instant and no way to say which is the
        archive's answer."""
        event_id = await store.upsert_event(db, builders.event())
        [yes_id, _] = await outcome_ids(db, event_id)

        await store.record_samples(
            db,
            [Sample(outcome_id=yes_id, observed_at=NOON, midpoint=Decimal("0.5"),
                    last_trade=Decimal("0.49"), source=Surface.GAMMA)],
        )
        # A backfill carries a midpoint and no last trade.
        await store.record_samples(
            db,
            [Sample(outcome_id=yes_id, observed_at=NOON, midpoint=Decimal("0.52"),
                    source=Surface.CLOB)],
        )

        [sample] = await store.history(db, yes_id, since=NOON, until=NOON)
        assert sample.midpoint == Decimal("0.520000")
        # Not erased by a write that did not carry one.
        assert sample.last_trade == Decimal("0.490000")
        assert sample.source is Surface.CLOB

    @pytest.mark.db
    async def test_history_comes_back_oldest_first(self, db) -> None:
        event_id = await store.upsert_event(db, builders.event())
        [yes_id, _] = await outcome_ids(db, event_id)
        await store.record_samples(
            db,
            [
                Sample(outcome_id=yes_id, observed_at=NOON + timedelta(minutes=n),
                       midpoint=Decimal("0.5"), source=Surface.GAMMA)
                for n in (3, 1, 2)
            ],
        )

        series = await store.history(db, yes_id, since=NOON, until=NOON + timedelta(hours=1))

        assert [s.observed_at for s in series] == sorted(s.observed_at for s in series)

    @pytest.mark.db
    async def test_a_sample_with_no_price_at_all_is_not_a_sample(self, db) -> None:
        """A failed read writes nothing. A placeholder — or the last known price repeated —
        makes a series that reads like a market standing still rather than collection that
        failed."""
        with pytest.raises(ValueError, match="not a price"):
            Sample(outcome_id=1, observed_at=NOON, source=Surface.GAMMA)

    @pytest.mark.db
    async def test_the_snapshot_is_one_query_over_every_tracked_outcome(self, db) -> None:
        event_id = await store.upsert_event(
            db,
            builders.event(
                markets=(
                    builders.binary_market("A?"),
                    builders.multi_outcome_market("B?", ("X", "Y", "Z")),
                )
            ),
        )
        ids = await outcome_ids(db, event_id)
        await store.record_samples(
            db,
            [
                Sample(outcome_id=i, observed_at=NOON - timedelta(minutes=5),
                       midpoint=Decimal("0.1"), source=Surface.GAMMA)
                for i in ids
            ]
            + [
                Sample(outcome_id=i, observed_at=NOON, midpoint=Decimal("0.2"),
                       source=Surface.GAMMA)
                for i in ids
            ],
        )

        latest = await store.latest_samples(db)

        assert set(latest) == set(ids)
        assert all(sample.observed_at == NOON for sample in latest.values())

    @pytest.mark.db
    async def test_a_removed_observation_is_out_of_the_snapshot_and_out_of_the_history(
        self, db
    ) -> None:
        """Both, and that is the point: there is no longer a state where the snapshot has
        dropped an event whose history is still readable."""
        event_id = await store.upsert_event(db, builders.event(provider_event_id="e-4"))
        [yes_id, _] = await outcome_ids(db, event_id)
        await store.record_samples(
            db,
            [Sample(outcome_id=yes_id, observed_at=NOON, midpoint=Decimal("0.3"),
                    source=Surface.GAMMA)],
        )

        assert await store.remove_event(db, "e-4")

        assert await store.latest_samples(db) == {}
        assert await store.history(db, yes_id, since=NOON, until=NOON) == []


class TestWhatWasActuallyCollected:
    @pytest.mark.db
    async def test_touching_windows_merge_into_one(self, db) -> None:
        """Two adjacent ranges left separate answer "not collected" for the instant between
        them — a gap this module would then try to fill for ever."""
        event_id = await store.upsert_event(db, builders.event())
        [yes_id, _] = await outcome_ids(db, event_id)

        await store.record_collected(db, yes_id, NOON, NOON + timedelta(hours=1))
        await store.record_collected(
            db, yes_id, NOON + timedelta(hours=1), NOON + timedelta(hours=2)
        )

        [merged] = await store.collected_ranges(db, yes_id)
        assert merged.starts_at == NOON
        assert merged.ends_at == NOON + timedelta(hours=2)
        assert await store.is_collected(db, yes_id, NOON + timedelta(minutes=90))

    @pytest.mark.db
    async def test_no_trade_and_no_collection_are_told_apart(self, db) -> None:
        event_id = await store.upsert_event(db, builders.event())
        [yes_id, _] = await outcome_ids(db, event_id)
        await store.record_collected(db, yes_id, NOON, NOON + timedelta(hours=1))

        # Inside the collected window and no sample: nobody traded.
        assert await store.is_collected(db, yes_id, NOON + timedelta(minutes=30))
        # Outside it: we were not looking.
        assert not await store.is_collected(db, yes_id, NOON + timedelta(hours=5))

    @pytest.mark.db
    async def test_the_oldest_boundary_only_moves_earlier(self, db) -> None:
        """A later read finding less is the provider being unhelpful, not history
        shrinking."""
        event_id = await store.upsert_event(db, builders.event())
        [yes_id, _] = await outcome_ids(db, event_id)

        await store.note_oldest_available(db, yes_id, NOON - timedelta(days=30))
        await store.note_oldest_available(db, yes_id, NOON - timedelta(days=5))

        assert await db.fetchval(
            "SELECT oldest_available_at FROM outcomes WHERE id = $1", yes_id
        ) == NOON - timedelta(days=30)

    @pytest.mark.db
    async def test_asking_for_older_data_lifts_the_boundary(self, db) -> None:
        event_id = await store.upsert_event(db, builders.event())
        [yes_id, _] = await outcome_ids(db, event_id)
        await store.note_oldest_available(db, yes_id, NOON)

        await store.clear_oldest_available(db, yes_id)

        assert await db.fetchval(
            "SELECT oldest_available_at FROM outcomes WHERE id = $1", yes_id
        ) is None


class TestDeletion:
    @pytest.mark.db
    async def test_samples_and_ranges_go_together(self, db) -> None:
        """A range surviving its samples is worse than either alone: it is binding on
        planning, so the window reads as already collected and backfill never returns."""
        event_id = await store.upsert_event(db, builders.event())
        [yes_id, no_id] = await outcome_ids(db, event_id)
        await store.record_samples(
            db,
            [
                Sample(outcome_id=i, observed_at=NOON, midpoint=Decimal("0.5"),
                       source=Surface.GAMMA)
                for i in (yes_id, no_id)
            ],
        )
        await store.record_collected(db, yes_id, NOON, NOON + timedelta(hours=1))

        samples, ranges = await store.delete_history(db, event_id)

        assert (samples, ranges) == (2, 1)
        assert await db.fetchval("SELECT count(*) FROM price_samples") == 0
        assert await db.fetchval("SELECT count(*) FROM collected_ranges") == 0
        # The observation itself survives. Deleting its data and removing it are still two
        # different acts — the second is the one that takes the event with it.
        assert len(await store.load_events(db)) == 1

    @pytest.mark.db
    async def test_a_deleted_period_stops_reading_as_collected(self, db) -> None:
        event_id = await store.upsert_event(db, builders.event())
        [yes_id, _] = await outcome_ids(db, event_id)
        await store.record_collected(db, yes_id, NOON, NOON + timedelta(hours=1))

        await store.delete_history(db, event_id)

        assert not await store.is_collected(db, yes_id, NOON + timedelta(minutes=30))


class TestGroups:
    @pytest.mark.db
    async def test_deleting_a_group_keeps_its_observations_and_their_data(self, db) -> None:
        group = await store.create_group(db, "tariffs")
        assert group.id is not None
        event_id = await store.upsert_event(db, builders.event(), group_id=group.id)
        [yes_id, _] = await outcome_ids(db, event_id)
        await store.record_samples(
            db,
            [Sample(outcome_id=yes_id, observed_at=NOON, midpoint=Decimal("0.5"),
                    source=Surface.GAMMA)],
        )

        assert await store.delete_group(db, group.id)

        [loaded] = await store.load_events(db)
        assert loaded.group_id is None
        assert await db.fetchval("SELECT count(*) FROM price_samples") == 1

    @pytest.mark.db
    async def test_creating_the_same_group_twice_is_not_an_error(self, db) -> None:
        """A model that asks again after a restart should not have to know whether it asked
        before."""
        first = await store.create_group(db, "tariffs")
        again = await store.create_group(db, "tariffs")

        assert first.id == again.id
        assert len(await store.list_groups(db)) == 1


class TestTheCeiling:
    @pytest.mark.db
    async def test_the_ceiling_refuses_and_changes_nothing(self, db) -> None:
        await store.upsert_event(db, builders.event(provider_event_id="e-a"))
        await store.upsert_event(db, builders.event(provider_event_id="e-b"))

        with pytest.raises(tracking.LimitReached, match="the operator's to do"):
            await tracking.track(db, builders.event(provider_event_id="e-c"),
                                 max_tracked_events=2)

        assert await store.count_tracked(db) == 2

    @pytest.mark.db
    async def test_an_event_already_tracked_is_refreshed_even_at_the_ceiling(self, db) -> None:
        """A refresh adds no traffic. Refusing it at the limit would leave a full archive
        unable to notice a market being added to an event it already holds."""
        await store.upsert_event(db, builders.event(provider_event_id="e-d"))

        _, already = await tracking.track(
            db, builders.event(provider_event_id="e-d"), max_tracked_events=1
        )

        assert already is True

    @pytest.mark.db
    async def test_removing_an_observation_frees_a_place(self, db) -> None:
        """The only way one is freed now, and the reason the refusal sends the model to the
        operator: freeing a place costs somebody's collected history."""
        await store.upsert_event(db, builders.event(provider_event_id="e-e"))
        await store.remove_event(db, "e-e")

        event_id, already = await tracking.track(
            db, builders.event(provider_event_id="e-f"), max_tracked_events=1
        )

        assert already is False
        assert event_id is not None
