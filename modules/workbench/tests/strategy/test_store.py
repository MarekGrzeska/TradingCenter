"""The store, against a real PostgreSQL — and the replay the whole record stands on."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from strategy import store
from strategy.catalogue import get
from strategy.spec import Decision

from .builders import crossing_facts

pytestmark = pytest.mark.db

BAR = datetime(2026, 8, 20, 10, 0, tzinfo=UTC)


async def a_parameter_set(db, strategy_id: str = "baseline_ma_cross", **params):
    return await store.add_parameter_set(db, strategy_id, params or {"fast_period": 20})


class TestParameterSets:
    async def test_versions_count_up_per_strategy(self, db) -> None:
        first = await store.add_parameter_set(db, "one", {"a": 1})
        second = await store.add_parameter_set(db, "one", {"a": 2})
        other = await store.add_parameter_set(db, "two", {"a": 3})

        assert (first.version, second.version, other.version) == (1, 2, 1)

    async def test_a_version_reads_back_as_it_was_written(self, db) -> None:
        """The point of append-only: a decision names a version, and answering "what was
        this decided with" requires that version to still read the way it read then."""
        written = await store.add_parameter_set(db, "one", {"fast_period": 20, "stop_atr": 2.5})

        read = await store.read_parameter_set(db, written.id)

        assert read is not None
        assert read.params == {"fast_period": 20, "stop_atr": 2.5}


class TestWatches:
    async def test_watching_the_same_pair_again_points_it_at_the_new_parameters(self, db) -> None:
        first = await a_parameter_set(db)
        second = await a_parameter_set(db)

        await store.put_watch(db, "baseline_ma_cross", "US100", first.id)
        watch = await store.put_watch(db, "baseline_ma_cross", "US100", second.id)

        assert watch.parameter_set_id == second.id
        assert len(await store.list_watches(db)) == 1

    async def test_asking_for_a_deactivated_watch_again_turns_it_back_on(self, db) -> None:
        """Asking for it is asking for it to run; whether a row already existed is this
        module's business, not the operator's."""
        params = await a_parameter_set(db)
        watch = await store.put_watch(db, "baseline_ma_cross", "US100", params.id)
        await store.set_watch_active(db, watch.id, False)

        again = await store.put_watch(db, "baseline_ma_cross", "US100", params.id)

        assert again.active is True

    async def test_deactivating_one_leaves_the_others_running(self, db) -> None:
        params = await a_parameter_set(db)
        one = await store.put_watch(db, "baseline_ma_cross", "US100", params.id)
        await store.put_watch(db, "baseline_ma_cross", "EURUSD", params.id)

        await store.set_watch_active(db, one.id, False)

        active = await store.list_watches(db, active_only=True)
        assert [watch.symbol for watch in active] == ["EURUSD"]


class TestDecisions:
    async def test_a_bar_is_decided_once(self, db) -> None:
        """What makes the loop idempotent: it re-reads the last closed bar on every wake,
        and a restart must not turn that into a second setup."""
        params = await a_parameter_set(db)
        decision = Decision.no_trade("nothing here")

        first = await store.record_decision(
            db,
            strategy_id="baseline_ma_cross",
            symbol="US100",
            parameter_set_id=params.id,
            as_of=BAR,
            decision=decision,
            reason_kind="strategy",
            facts={},
        )
        second = await store.record_decision(
            db,
            strategy_id="baseline_ma_cross",
            symbol="US100",
            parameter_set_id=params.id,
            as_of=BAR,
            decision=decision,
            reason_kind="strategy",
            facts={},
        )

        assert (first, second) == (True, False)

    async def test_a_refusal_for_want_of_data_reads_apart_from_the_strategys_own(self, db) -> None:
        """The two have different remedies — a backfill and a rethink — so they have to be
        distinguishable in the row, not only in the sentence."""
        params = await a_parameter_set(db)
        await store.record_decision(
            db,
            strategy_id="baseline_ma_cross",
            symbol="US100",
            parameter_set_id=params.id,
            as_of=BAR,
            decision=Decision.no_trade("the archive has not verified that stretch"),
            reason_kind="coverage",
            facts={},
        )

        recorded = await store.last_decision(db, "baseline_ma_cross", "US100")

        assert recorded is not None
        assert recorded.reason_kind == "coverage"

    async def test_a_decision_carries_whether_anybody_was_told(self, db) -> None:
        """The alert path decides on this field, so it has to survive the read. Absent means nobody
        knows about this setup — which is what makes the next bar try again."""
        params = await a_parameter_set(db)
        await store.record_decision(
            db,
            strategy_id="baseline_ma_cross",
            symbol="US100",
            parameter_set_id=params.id,
            as_of=BAR,
            decision=Decision.trade(direction="long", entry=100.0, stop=98.0, target=110.0),
            reason_kind=None,
            facts={},
        )
        before = await store.last_decision(db, "baseline_ma_cross", "US100")
        assert before is not None and before.notified_at is None

        await store.mark_decision_notified(db, before.id, at=BAR + timedelta(minutes=1))

        after = await store.last_decision(db, "baseline_ma_cross", "US100")
        assert after is not None and after.notified_at == BAR + timedelta(minutes=1)

    async def test_pending_setups_counts_only_trades(self, db) -> None:
        """The number a trigger compares against a threshold — counted from the recorded
        decisions, so it is the very fact the woken team will read."""
        params = await a_parameter_set(db)
        for index, decision in enumerate(
            (
                Decision.trade(direction="long", entry=100.0, stop=98.0, target=110.0),
                Decision.no_trade("nothing here"),
                Decision.trade(direction="long", entry=101.0, stop=99.0, target=111.0),
            )
        ):
            await store.record_decision(
                db,
                strategy_id="baseline_ma_cross",
                symbol="US100",
                parameter_set_id=params.id,
                as_of=BAR + timedelta(hours=index),
                decision=decision,
                reason_kind=None if decision.action == "trade" else "strategy",
                facts={},
            )

        assert await store.count_pending_setups(db, "baseline_ma_cross") == 2
        assert await store.count_pending_setups(db, "baseline_ma_cross", since=BAR + timedelta(hours=2)) == 1


class TestReplay:
    async def test_a_recorded_decision_decides_the_same_way_again(self, db) -> None:
        """A recorded decision is evidence only if it can be re-decided. The snapshot goes back into the
        very same `evaluate`, with no archive involved."""
        spec = get("baseline_ma_cross")
        resolved = spec.resolve_params()
        facts = crossing_facts(fast=[99.0, 101.0], slow=[100.0, 100.0], atr=[2.0, 2.0])
        original = spec.evaluate(facts, resolved)
        params = await a_parameter_set(db)

        await store.record_decision(
            db,
            strategy_id=spec.id,
            symbol="US100",
            parameter_set_id=params.id,
            as_of=facts.as_of,
            decision=original,
            reason_kind=None,
            facts=store.facts_snapshot(facts),
        )
        recorded = await store.last_decision(db, spec.id, "US100")
        assert recorded is not None

        replayed = spec.evaluate(store.facts_from_snapshot(recorded.facts), resolved)

        assert replayed == original
        assert recorded.decision.entry == original.entry
        assert recorded.decision.rr == original.rr
