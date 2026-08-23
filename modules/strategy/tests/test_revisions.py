"""Provenance, end to end: which rule decided, with which numbers, on which readings.

The test that matters most here is the last one. A recorded decision is evidence only if it
can be re-decided from what was written down — its revision, its parameter set and its
snapshot — without asking the archive anything and without reading the definition's current
wording (`strategy-runtime`, "Odtworzenie oceny po zmianie definicji").
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from builders import crossing_facts
from fakes import FakeArchive

from strategy import resolver, store
from strategy.catalogue.baseline_rule import BASELINE_RULE
from strategy.errors import StrategyError, UnknownRevision
from strategy.interpreter import interpret
from strategy.runner.loop import evaluate_once
from strategy.store import facts_from_snapshot

pytestmark = pytest.mark.db

BAR = datetime(2026, 8, 20, 10, 0, tzinfo=UTC)

# The rule of reference, written down — so a test about revisions is not also a test about
# whether some invented rule means anything.
RULE = BASELINE_RULE.model_dump(mode="json")


def a_different_rule() -> dict:
    """The same rule with one number moved, so two revisions are told apart by an answer."""
    changed = BASELINE_RULE.model_copy(deep=True)
    changed.params[3].default = 4.0  # stop_atr, which moves the stop and so the reward
    return changed.model_dump(mode="json")


async def a_written_strategy(conn, definition: dict | None = None):
    return await store.add_definition(
        conn,
        strategy_id="written_cross",
        name="Written · moving-average cross",
        description="the rule of reference, clicked together",
        definition=definition or RULE,
    )


async def a_watch_on(conn, revision, *, symbol: str = "US100"):
    """A watch pinned to one revision, with the parameter set the route would have written.

    Resolved defaults rather than an empty set: `/parameter-sets` resolves before it stores,
    so a set of raw `{}` is a row nothing in this module produces.
    """
    found = await resolver.resolve(conn, revision.strategy_id, revision_id=revision.id)
    params = await store.add_parameter_set(
        conn,
        revision.strategy_id,
        found.spec.resolve_params(),
        strategy_revision_id=revision.id,
    )
    return await store.put_watch(
        conn, revision.strategy_id, symbol, params.id, strategy_revision_id=revision.id
    )


def crossing():
    return crossing_facts(fast=[99.0, 101.0], slow=[100.0, 100.0], atr=[2.0, 2.0])


class TestResolving:
    async def test_a_written_rule_becomes_an_ordinary_entry(self, db) -> None:
        await a_written_strategy(db)

        found = await resolver.resolve(db, "written_cross")

        assert found.spec.indicators == ("ema", "atr")
        assert found.revision is not None
        assert found.revision.version == 1

    async def test_a_coded_entry_asked_for_a_revision_is_refused(self, db) -> None:
        """A caller believing something untrue about which kind of strategy this is.
        Answering with the code anyway would leave that belief in place."""
        with pytest.raises(StrategyError, match="no revisions"):
            await resolver.resolve(db, "baseline_ma_cross", version=1)

    async def test_a_revision_that_was_never_written_is_refused_by_number(self, db) -> None:
        await a_written_strategy(db)

        with pytest.raises(UnknownRevision):
            await resolver.resolve(db, "written_cross", version=7)

    async def test_both_sources_are_one_catalogue(self, db) -> None:
        await a_written_strategy(db)

        found = await resolver.all_available(db)

        assert {one.spec.id for one in found} == {"baseline_ma_cross", "written_cross"}
        assert {one.from_code for one in found} == {True, False}

    async def test_a_revision_this_image_cannot_read_is_left_out_of_the_list(self, db) -> None:
        """A rollback below the image that wrote a rule is ordinary. The rest of the
        catalogue is unaffected, and a caller listing strategies is not who should hear it."""
        broken = {**RULE, "setups": [{**RULE["setups"][0], "when": {"node": "sorcery"}}]}
        await store.add_definition(
            conn=db, strategy_id="from_the_future", name="n", description="", definition=broken
        )

        found = await resolver.all_available(db)

        assert {one.spec.id for one in found} == {"baseline_ma_cross"}


class TestPinning:
    async def test_a_watch_keeps_computing_the_revision_it_was_started_with(self, pool) -> None:
        """The whole of decision 7: a rule swapped underfoot produces decisions from before
        and after the change that look comparable and are not."""
        async with pool.acquire() as conn:
            _, first = await a_written_strategy(conn)
            watch = await a_watch_on(conn, first)
            await store.add_revision(conn, "written_cross", a_different_rule())

        async with pool.acquire() as conn:
            found = await resolver.resolve_watch(conn, watch)

        assert found.revision is not None
        assert found.revision.version == 1

    async def test_a_parameter_set_from_another_revision_is_refused_naming_both(
        self, api, app, pool
    ) -> None:
        """A value inside its range under one revision may be outside it — or have no
        declaration at all — under the next, so reusing the set silently would run a
        strategy on numbers nothing vouches for."""
        app.state.archive = FakeArchive()
        async with pool.acquire() as conn:
            _, first = await a_written_strategy(conn)
            await store.add_revision(conn, "written_cross", a_different_rule())
            params = await store.add_parameter_set(
                conn, "written_cross", {}, strategy_revision_id=first.id
            )

        response = await api.post(
            "/watches",
            json={
                "strategy_id": "written_cross",
                "symbol": "US100",
                "parameter_set_id": params.id,
            },
        )

        assert response.status_code == 422
        assert "belongs to revision" in response.json()["detail"]

    async def test_a_watch_pins_the_newest_revision_when_none_is_named(
        self, api, app, pool
    ) -> None:
        app.state.archive = FakeArchive()
        async with pool.acquire() as conn:
            await a_written_strategy(conn)
            second = await store.add_revision(conn, "written_cross", a_different_rule())
        assert second is not None

        response = await api.post(
            "/watches", json={"strategy_id": "written_cross", "symbol": "US100"}
        )

        assert response.json()["strategy_revision_id"] == second.id

    async def test_a_watch_may_be_pinned_to_an_older_revision_on_purpose(
        self, api, app, pool
    ) -> None:
        app.state.archive = FakeArchive()
        async with pool.acquire() as conn:
            _, first = await a_written_strategy(conn)
            await store.add_revision(conn, "written_cross", a_different_rule())

        response = await api.post(
            "/watches",
            json={"strategy_id": "written_cross", "symbol": "US100", "revision": 1},
        )

        assert response.json()["strategy_revision_id"] == first.id


class TestWhatOneDecisionRemembers:
    async def test_a_decision_names_the_revision_that_made_it(self, pool) -> None:
        async with pool.acquire() as conn:
            _, revision = await a_written_strategy(conn)
            watch = await a_watch_on(conn, revision)

        await evaluate_once(pool, FakeArchive(last_bar=BAR, facts=crossing()), watch)

        async with pool.acquire() as conn:
            recorded = await store.last_decision(conn, "written_cross", "US100")
        assert recorded is not None
        assert recorded.strategy_revision_id == revision.id
        assert recorded.strategy_revision == 1

    async def test_a_decision_by_a_coded_entry_names_no_revision(self, pool) -> None:
        """`None` means what it says — the rule is in the repository under that id — rather
        than standing in for a value nobody wrote."""
        async with pool.acquire() as conn:
            params = await store.add_parameter_set(conn, "baseline_ma_cross", {})
            watch = await store.put_watch(conn, "baseline_ma_cross", "US100", params.id)

        await evaluate_once(pool, FakeArchive(last_bar=BAR, facts=crossing()), watch)

        async with pool.acquire() as conn:
            recorded = await store.last_decision(conn, "baseline_ma_cross", "US100")
        assert recorded is not None
        assert recorded.strategy_revision_id is None

    async def test_a_recorded_decision_is_re_decided_from_what_was_written_down(
        self, pool
    ) -> None:
        """The acceptance test of this whole change. The definition moves on afterwards, and
        the replay still lands on the decision that was recorded — because it reads the
        revision the decision names, not the newest one."""
        async with pool.acquire() as conn:
            _, revision = await a_written_strategy(conn)
            watch = await a_watch_on(conn, revision)
        await evaluate_once(pool, FakeArchive(last_bar=BAR, facts=crossing()), watch)
        async with pool.acquire() as conn:
            await store.add_revision(conn, "written_cross", a_different_rule())
            recorded = await store.last_decision(conn, "written_cross", "US100")
            assert recorded is not None
            assert recorded.strategy_revision_id is not None
            its_revision = await store.read_revision(conn, recorded.strategy_revision_id)
            its_params = await store.read_parameter_set(conn, recorded.parameter_set_id)

        assert its_revision is not None and its_params is not None
        again = interpret(
            resolver.parse(its_revision),
            facts_from_snapshot(recorded.facts),
            its_params.params,
        )

        assert again == recorded.decision
