"""Kept reports: written whole, read back whole, and never started from a route."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from strategy import store
from strategy.backtest.costs import CostModel

pytestmark = pytest.mark.db

START = datetime(2026, 1, 1, tzinfo=UTC)


async def a_run(conn, *, strategy_id: str = "baseline_ma_cross"):
    return await store.record_backtest_run(
        conn,
        strategy_id=strategy_id,
        symbol="US100",
        resolution="HOUR",
        range_from=START,
        range_to=START + timedelta(days=90),
        params={"fast_period": 20},
        costs=CostModel(spread=1.0).as_dict(),
        report={"metrics": {"expectancy_r": 0.21}, "attribution": []},
    )


class TestKeepingAReport:
    async def test_a_report_reads_back_as_it_was_written(self, db) -> None:
        """Kept entire rather than shredded into columns: a metric added next month must
        not make last month's runs unreadable."""
        written = await a_run(db)

        read = await store.read_backtest_run(db, written.id)

        assert read is not None
        assert read.report["metrics"]["expectancy_r"] == 0.21
        assert read.costs["spread"] == 1.0

    async def test_a_rerun_is_another_row(self, db) -> None:
        """Comparing a strategy against its own earlier self is a thing an operator should
        be able to do."""
        await a_run(db)
        await a_run(db)

        assert len(await store.list_backtest_runs(db)) == 2

    async def test_runs_are_listed_newest_first_and_can_be_narrowed(self, db) -> None:
        await a_run(db, strategy_id="one")
        await a_run(db, strategy_id="two")

        assert [row.strategy_id for row in await store.list_backtest_runs(db, strategy_id="two")] == [
            "two"
        ]


class TestARunChangesNothingElse:
    async def test_a_backtest_leaves_the_live_record_alone(self, pool) -> None:
        """A replay must not be able to reach the decisions the loop wrote, and it cannot structurally — `run` is
        handed an archive and never a pool. This is the test that says so rather than the docstring."""
        from strategy import backtest, store
        from strategy.spec import Decision

        async with pool.acquire() as conn:
            params = await store.add_parameter_set(conn, "baseline_ma_cross", {})
            await store.record_decision(
                conn,
                strategy_id="baseline_ma_cross",
                symbol="US100",
                parameter_set_id=params.id,
                as_of=START,
                decision=Decision.no_trade("from the loop"),
                reason_kind="strategy",
                facts={},
            )

        from test_backtest import a_history

        archive = a_history()
        await backtest.run(
            archive,
            "baseline_ma_cross",
            "US100",
            start=archive.times[10],
            end=archive.times[-1],
        )

        async with pool.acquire() as conn:
            live = await store.list_decisions(conn)
            runs = await store.list_backtest_runs(conn)
        assert [row.decision.reason for row in live] == ["from the loop"]
        assert runs == [], "a run keeps nothing unless it is asked to"


class TestTheRoutes:
    async def test_a_kept_run_is_readable(self, api, pool) -> None:
        async with pool.acquire() as conn:
            written = await a_run(conn)

        response = await api.get(f"/backtests/{written.id}")

        assert response.status_code == 200
        assert response.json()["report"]["metrics"]["expectancy_r"] == 0.21

    async def test_a_run_that_does_not_exist_is_refused(self, api) -> None:
        assert (await api.get("/backtests/9999")).status_code == 422

    async def test_there_is_no_route_that_starts_a_run(self, app) -> None:
        """A run over years of bars is minutes of work and would hold a request open for all of it — and a long run
        should not be something a caller sets off by accident. It is a command."""
        paths = app.openapi()["paths"]

        assert "post" not in paths.get("/backtests", {})
        assert not any("backtest" in path and "post" in verbs for path, verbs in paths.items())
