"""The REST contract: a happy path, an error and a refusal per view."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from strategy import store
from strategy.spec import Decision

from .fakes import FakeArchive

pytestmark = pytest.mark.db

BAR = datetime(2026, 8, 20, 10, 0, tzinfo=UTC)


@pytest.fixture
def api_with_archive(api, app):
    app.state.archive = FakeArchive()
    return api


class TestTheCatalogue:
    async def test_the_strategies_are_the_ones_in_the_image(self, api) -> None:
        response = await api.get("/strategies")

        assert response.status_code == 200
        assert "baseline_ma_cross" in {row["id"] for row in response.json()}

    async def test_one_strategy_reads_back_with_its_facts_and_ranges(self, api) -> None:
        response = await api.get("/strategies/baseline_ma_cross")

        body = response.json()
        assert {fact["key"] for fact in body["facts"]} == {"fast", "slow", "range"}
        assert {param["name"] for param in body["params"]} >= {"fast_period", "stop_atr"}

    async def test_a_strategy_this_image_does_not_carry_is_a_404(self, api) -> None:
        response = await api.get("/strategies/no_such_strategy")

        assert response.status_code == 404
        assert "no_such_strategy" in response.json()["detail"]


class TestAPlatformWatchingNothing:
    async def test_the_surfaces_answer_empty_rather_than_failing(self, api) -> None:
        """Zero is a supported state, not a degraded one. Every list answers with nothing
        in it, and `/health` reports the count without treating it as a problem."""
        for path in ("/watches", "/decisions", "/parameter-sets", "/backtests"):
            response = await api.get(path)
            assert response.status_code == 200, path
            assert response.json() == [], path

        health = await api.get("/health")
        assert health.status_code == 200
        assert health.json()["watching"] == 0


class TestParameterSets:
    async def test_a_set_is_stored_resolved(self, api) -> None:
        """What is written down is what would be used, not what was typed."""
        response = await api.post(
            "/parameter-sets", json={"strategy_id": "baseline_ma_cross", "params": {"fast_period": 8}}
        )

        assert response.status_code == 201
        body = response.json()
        assert body["version"] == 1
        assert body["params"]["fast_period"] == 8
        assert body["params"]["stop_atr"] == 2.0  # the default, filled in

    async def test_a_value_out_of_range_is_refused_now_rather_than_at_the_next_bar(
        self, api
    ) -> None:
        response = await api.post(
            "/parameter-sets",
            json={"strategy_id": "baseline_ma_cross", "params": {"fast_period": 9999}},
        )

        assert response.status_code == 422
        assert "fast_period" in response.json()["detail"]

    async def test_versions_count_up(self, api) -> None:
        body = {"strategy_id": "baseline_ma_cross", "params": {}}
        await api.post("/parameter-sets", json=body)
        second = await api.post("/parameter-sets", json=body)

        assert second.json()["version"] == 2


class TestWatches:
    async def test_watching_a_pair_writes_a_parameter_set_when_none_is_given(
        self, api_with_archive
    ) -> None:
        response = await api_with_archive.post(
            "/watches", json={"strategy_id": "baseline_ma_cross", "symbol": "US100"}
        )

        assert response.status_code == 201
        assert response.json()["active"] is True
        assert response.json()["parameter_set_id"] > 0

    async def test_a_strategy_whose_facts_the_archive_does_not_announce_is_refused(
        self, api, app
    ) -> None:
        """Registration is where a strategy's facts are checked against what the archive actually has. Refused by
        name, because the remedy is either a spelling fix or an indicator the archive has to grow."""
        app.state.archive = FakeArchive(indicators=frozenset({"ema"}))

        response = await api.post(
            "/watches", json={"strategy_id": "baseline_ma_cross", "symbol": "US100"}
        )

        assert response.status_code == 422
        assert "atr" in response.json()["detail"]

    async def test_a_parameter_set_belonging_to_another_strategy_is_refused(
        self, api_with_archive, pool
    ) -> None:
        async with pool.acquire() as conn:
            other = await store.add_parameter_set(conn, "somebody_else", {})

        response = await api_with_archive.post(
            "/watches",
            json={
                "strategy_id": "baseline_ma_cross",
                "symbol": "US100",
                "parameter_set_id": other.id,
            },
        )

        assert response.status_code == 422

    async def test_deactivating_a_watch_leaves_the_others_running(
        self, api_with_archive
    ) -> None:
        one = await api_with_archive.post(
            "/watches", json={"strategy_id": "baseline_ma_cross", "symbol": "US100"}
        )
        await api_with_archive.post(
            "/watches", json={"strategy_id": "baseline_ma_cross", "symbol": "EURUSD"}
        )

        response = await api_with_archive.patch(
            f"/watches/{one.json()['id']}", json={"active": False}
        )

        assert response.status_code == 200
        assert response.json()["active"] is False
        active = await api_with_archive.get("/watches", params={"active_only": True})
        assert [row["symbol"] for row in active.json()] == ["EURUSD"]

    async def test_a_watch_that_does_not_exist_is_refused(self, api) -> None:
        response = await api.patch("/watches/9999", json={"active": False})

        assert response.status_code == 422


class TestDecisions:
    async def _record(self, pool, decision: Decision, *, reason_kind=None, facts=None):
        async with pool.acquire() as conn:
            params = await store.add_parameter_set(conn, "baseline_ma_cross", {})
            await store.record_decision(
                conn,
                strategy_id="baseline_ma_cross",
                symbol="US100",
                parameter_set_id=params.id,
                as_of=BAR,
                decision=decision,
                reason_kind=reason_kind,
                facts=facts or {},
            )

    async def test_refusals_are_listed_too(self, api, pool) -> None:
        """"The system has not traded in three weeks" is answered by reading them; a list
        that showed only setups would answer it with silence."""
        await self._record(pool, Decision.no_trade("nothing here"), reason_kind="strategy")

        response = await api.get("/decisions")

        assert response.status_code == 200
        assert response.json()[0]["reason"] == "nothing here"
        assert response.json()[0]["reason_kind"] == "strategy"

    async def test_one_decision_carries_the_readings_it_stood_on(self, api, pool) -> None:
        await self._record(
            pool,
            Decision.trade(direction="long", entry=100.0, stop=98.0, target=110.0),
            facts={"symbol": "US100", "values": {}},
        )
        listed = await api.get("/decisions")

        response = await api.get(f"/decisions/{listed.json()[0]['id']}")

        assert response.status_code == 200
        assert response.json()["facts"]["symbol"] == "US100"
        assert response.json()["rr"] == 5.0

    async def test_a_decision_names_the_parameter_version_it_was_decided_under(
        self, api, pool
    ) -> None:
        """And that version still reads the way it read then, resolved. Written through the route rather
        than into the store, because that is where a parameter set is resolved."""
        written = await api.post(
            "/parameter-sets", json={"strategy_id": "baseline_ma_cross", "params": {}}
        )
        parameter_set_id = written.json()["id"]
        async with pool.acquire() as conn:
            await store.record_decision(
                conn,
                strategy_id="baseline_ma_cross",
                symbol="US100",
                parameter_set_id=parameter_set_id,
                as_of=BAR,
                decision=Decision.no_trade("nothing here"),
                reason_kind="strategy",
                facts={},
            )

        listed = await api.get("/decisions")
        assert listed.json()[0]["parameter_set_id"] == parameter_set_id

        sets = await api.get("/parameter-sets", params={"strategy_id": "baseline_ma_cross"})
        named = [row for row in sets.json() if row["id"] == parameter_set_id]
        assert named, "the decision names a parameter set that cannot be read back"
        assert named[0]["params"]["fast_period"] == 20

    async def test_a_decision_that_does_not_exist_is_refused(self, api) -> None:
        response = await api.get("/decisions/9999")

        assert response.status_code == 422

    async def test_a_limit_over_the_ceiling_is_refused_by_the_route(self, api) -> None:
        response = await api.get("/decisions", params={"limit": 10_000})

        assert response.status_code == 422
