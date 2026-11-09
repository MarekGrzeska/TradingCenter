"""The two reads and one write a step's recipe leans on in the database: one attempt per key, and the team's own placed
orders. The recipe that uses them is `test_strategy_execute.py`."""

from __future__ import annotations

from decimal import Decimal

import asyncpg
import pytest

from teams import store
from teams.contract import AgentDefinition, TeamDefinition

pytestmark = pytest.mark.db

OWNER = "operator-1"


async def _step_row(conn: asyncpg.Connection) -> tuple[int, int, int]:
    definition = TeamDefinition(
        agents=[AgentDefinition(key="trader", role="t", prompt="p", model_id="gpt-6-luna")]
    )
    team, revision = await store.create_team(
        conn, owner_principal=OWNER, name="a team", description="", definition=definition
    )
    run, _ = await store.create_run(
        conn, team_revision_id=revision["id"], owner_principal=OWNER, agent_keys=["trader"]
    )
    step = await store.start_step(conn, run_id=run["id"], agent_key="trader")
    return team["id"], run["id"], step["id"]


async def _order(conn, run_id: int, step_id: int, *, key: str | None, symbol: str = "US100") -> asyncpg.Record:
    return await store.record_trade(
        conn,
        run_id=run_id,
        run_step_id=step_id,
        agent_key="trader",
        tool_name="place_order",
        symbol=symbol,
        direction="BUY",
        size=Decimal("0.1"),
        level=None,
        attempt_key=key,
    )


async def test_an_attempt_key_is_used_once_and_the_second_write_leaves_no_row(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        _team, run_id, step_id = await _step_row(conn)
        await _order(conn, run_id, step_id, key="7:execute:5:1:2026-11-09T14:35:00Z:enter")
        with pytest.raises(store.AttemptAlreadyMade):
            await _order(conn, run_id, step_id, key="7:execute:5:1:2026-11-09T14:35:00Z:enter")
        await _order(conn, run_id, step_id, key=None)
        await _order(conn, run_id, step_id, key=None)
        rows = await store.get_run_trades(conn, run_id=run_id)
    assert len(rows) == 3


async def test_the_team_placed_orders_are_its_own_taken_orders_on_the_symbol(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        team_id, run_id, step_id = await _step_row(conn)
        taken = await _order(conn, run_id, step_id, key=None)
        await store.settle_trade(
            conn, trade_id=taken["id"], status="settled", result_status="ACCEPTED",
            provider_order_id="deal-1", reference="ref-1",
        )
        refused = await _order(conn, run_id, step_id, key=None)
        await store.settle_trade(
            conn, trade_id=refused["id"], status="refused", result_status=None,
            provider_order_id=None, reference=None,
        )
        other_symbol = await _order(conn, run_id, step_id, key=None, symbol="GOLD")
        await store.settle_trade(
            conn, trade_id=other_symbol["id"], status="settled", result_status="ACCEPTED",
            provider_order_id="deal-2", reference=None,
        )
        mine = await store.team_placed_orders(conn, team_id=team_id, owner_principal=OWNER, symbol="US100")
        theirs = await store.team_placed_orders(
            conn, team_id=team_id, owner_principal="somebody-else", symbol="US100"
        )
    assert [row["provider_order_id"] for row in mine] == ["deal-1"]
    assert theirs == []
