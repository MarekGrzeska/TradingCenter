"""The tool surface: what it announces, and what it answers. Driven against the real store, because every tool here
is a read of it and doubling that would leave the queries untested while looking like coverage."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from strategy import store
from strategy.mcp_app import build_server
from strategy.spec import Decision

pytestmark = pytest.mark.db

NOW = datetime.now(tz=UTC)


@pytest.fixture
def tool_server(pool):
    """A server whose tools read the throwaway database."""

    class _State:
        def __init__(self, pool) -> None:
            self.pool = pool

    class _App:
        def __init__(self, pool) -> None:
            self.state = _State(pool)

    return build_server(_App(pool))


async def a_trade(pool, *, strategy_id="baseline_ma_cross", symbol="US100", at=None):
    async with pool.acquire() as conn:
        params = await store.add_parameter_set(conn, strategy_id, {})
        await store.record_decision(
            conn,
            strategy_id=strategy_id,
            symbol=symbol,
            parameter_set_id=params.id,
            as_of=at or NOW - timedelta(minutes=5),
            decision=Decision.trade(direction="long", entry=100.0, stop=98.0, target=110.0),
            reason_kind=None,
            facts={},
        )


async def a_refusal(pool, *, symbol="US100", at=None, kind="strategy"):
    async with pool.acquire() as conn:
        params = await store.add_parameter_set(conn, "baseline_ma_cross", {})
        await store.record_decision(
            conn,
            strategy_id="baseline_ma_cross",
            symbol=symbol,
            parameter_set_id=params.id,
            as_of=at or NOW - timedelta(minutes=10),
            decision=Decision.no_trade("nothing here"),
            reason_kind=kind,
            facts={},
        )


async def call(server, name: str, **arguments):
    _content, structured = await server.call_tool(name, arguments)
    return structured


class TestTheSurfaceOnlyReads:
    async def test_every_announced_tool_says_so_structurally(self, tool_server) -> None:
        """An annotation is a claim an MCP client can act on, not a convention this module follows. Asserted of the
        announced list rather than of the source, so a tool added without it fails here."""
        for tool in await tool_server.list_tools():
            assert tool.annotations is not None, tool.name
            assert tool.annotations.readOnlyHint is True, tool.name
            assert tool.annotations.destructiveHint is False, tool.name

    async def test_there_is_no_tool_that_changes_anything(self, tool_server) -> None:
        """Activating a strategy, writing a parameter set and running a backtest are the operator's, over REST. A
        model asking for one should find nothing to call — the module's scope, not a momentary refusal."""
        announced = {tool.name for tool in await tool_server.list_tools()}

        assert announced == {
            "list_strategies",
            "pending_setups",
            "recent_decisions",
            "last_decision",
        }


class TestPendingSetups:
    async def test_the_count_is_the_field_a_trigger_watches(self, tool_server, pool) -> None:
        await a_trade(pool)
        await a_trade(pool, at=NOW - timedelta(minutes=3))
        await a_refusal(pool)

        answer = await call(tool_server, "pending_setups", strategy_id="baseline_ma_cross")

        assert answer["pending"] == 2
        assert answer["newest_at"] is not None

    async def test_a_strategy_standing_on_nothing_answers_zero_not_an_error(
        self, tool_server
    ) -> None:
        """Zero is the ordinary answer, and a trigger comparing it against a threshold has
        to be able to read it."""
        answer = await call(tool_server, "pending_setups", strategy_id="baseline_ma_cross")

        assert answer["pending"] == 0
        assert answer["newest_at"] is None

    async def test_a_setup_older_than_the_window_is_history(self, tool_server, pool) -> None:
        await a_trade(pool, at=NOW - timedelta(days=10))

        answer = await call(
            tool_server, "pending_setups", strategy_id="baseline_ma_cross", window_hours=24
        )

        assert answer["pending"] == 0

    async def test_the_number_is_the_one_the_woken_team_will_read(self, tool_server, pool) -> None:
        """The seam this whole surface is shaped around. A trigger reacting to one value
        while the team it starts reads another is worse than no trigger at all."""
        await a_trade(pool)

        counted = await call(tool_server, "pending_setups", strategy_id="baseline_ma_cross")
        read = await call(
            tool_server, "recent_decisions", strategy_id="baseline_ma_cross", only_setups=True
        )

        assert counted["pending"] == len(read["result"])


class TestReadingDecisions:
    async def test_refusals_are_included_by_default(self, tool_server, pool) -> None:
        await a_trade(pool)
        await a_refusal(pool)

        rows = (await call(tool_server, "recent_decisions", strategy_id="baseline_ma_cross"))["result"]

        assert {row["action"] for row in rows} == {"trade", "no_trade"}
        assert any(row["reason_kind"] == "strategy" for row in rows)

    async def test_only_setups_narrows_to_the_tradeable_ones(self, tool_server, pool) -> None:
        await a_trade(pool)
        await a_refusal(pool)

        rows = (
            await call(
                tool_server, "recent_decisions", strategy_id="baseline_ma_cross", only_setups=True
            )
        )["result"]

        assert [row["action"] for row in rows] == ["trade"]

    async def test_a_pair_never_decided_answers_nothing_rather_than_failing(
        self, tool_server
    ) -> None:
        """A watch that has just been created has not reached its first closed bar."""
        answer = await call(
            tool_server, "last_decision", strategy_id="baseline_ma_cross", symbol="US100"
        )

        assert answer["result"] is None

    async def test_the_last_decision_for_a_pair_is_the_newest_one(self, tool_server, pool) -> None:
        await a_refusal(pool, at=NOW - timedelta(hours=2))
        await a_trade(pool, at=NOW - timedelta(minutes=1))

        answer = await call(
            tool_server, "last_decision", strategy_id="baseline_ma_cross", symbol="US100"
        )

        assert answer["result"]["action"] == "trade"


class TestTheCatalogueTool:
    async def test_it_lists_what_the_image_carries(self, tool_server) -> None:
        rows = (await call(tool_server, "list_strategies"))["result"]

        assert "baseline_ma_cross" in {row["id"] for row in rows}
