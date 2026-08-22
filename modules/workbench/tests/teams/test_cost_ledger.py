"""The ledger against a real database: what a run's cost stops, and what a changed price
list does not move."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import asyncpg
import pytest

from teams import store
from teams.contract import AgentDefinition, CostLimits, TeamDefinition, TeamEdge
from teams.models_catalogue import ModelCatalogue
from teams.runner import RunRegistry, execute_run
from teams.tools import ToolServerRegistry

from .mcp_stand_in import settings_for
from .scripted_provider import ScriptedProvider, says

pytestmark = pytest.mark.db

OWNER = "operator-1"

# With the catalogue below (1 per 1M in, 6 per 1M out) a 100/20-token call costs
# 0.0001 + 0.00012 = 0.00022. Every limit in this file is written against that number
# rather than a round one, so a test that fails says which call went through.
ONE_CALL = Decimal("0.00022")


def an_agent(key: str) -> AgentDefinition:
    return AgentDefinition(key=key, role=key, prompt=f"be the {key}", model_id="gpt-5.6-luna")


async def _run(
    pool: asyncpg.Pool, definition: TeamDefinition, provider, *, owner: str = OWNER
) -> tuple[int, int]:
    async with pool.acquire() as conn:
        team, revision = await store.create_team(
            conn, owner_principal=owner, name="a team", description="", definition=definition
        )
        run, _ = await store.create_run(
            conn,
            team_revision_id=revision["id"],
            owner_principal=owner,
            agent_keys=[agent.key for agent in definition.agents],
        )
    settings = settings_for(None)
    await execute_run(
        pool,
        run_id=run["id"],
        team_id=team["id"],
        owner_principal=OWNER,
        definition=definition,
        provider=provider,
        tool_registry=ToolServerRegistry.from_settings(settings),
        catalogue=ModelCatalogue.from_settings(settings),
        settings=settings,
        registry=RunRegistry(),
    )
    return team["id"], run["id"]


async def test_a_run_that_reaches_its_limit_stops_and_says_so(pool: asyncpg.Pool) -> None:
    """specs/teams-usage, "Przebieg dobija do granicy w połowie pracy"."""
    definition = TeamDefinition(
        agents=[an_agent("scout"), an_agent("judge")],
        edges=[TeamEdge(from_="scout", to="judge")],
        # Below what one call costs, so the scout's call goes through (nothing is spent
        # when it is checked) and the judge's is refused.
        limits=CostLimits(run_limit="0.0002"),
    )
    provider = ScriptedProvider(by_role={"scout": says("up"), "judge": says("never asked")})

    _, run_id = await _run(pool, definition, provider)

    async with pool.acquire() as conn:
        run = await store.get_run(conn, run_id=run_id, owner_principal=OWNER)
        steps = {row["agent_key"]: dict(row) for row in await store.get_run_steps(conn, run_id=run_id)}
        rows = await conn.fetch("SELECT * FROM usage WHERE run_id = $1", run_id)

    assert run is not None
    assert run["status"] == "failed"
    assert "cost limit" in run["stopped_reason"]
    assert "0.0002" in run["stopped_reason"]
    # What happened before the ceiling stays written (specs/teams-usage, "ślad tego, co
    # zdążyło się wydarzyć, pozostaje zapisany").
    assert steps["scout"]["status"] == "completed"
    assert steps["scout"]["output"] == "up"
    assert steps["judge"]["status"] == "failed"
    # And the judge was never called, so it left no usage row.
    assert len(rows) == 1
    assert provider.asks_for("judge") == []


async def test_a_team_with_no_limits_is_never_stopped_for_cost(pool: asyncpg.Pool) -> None:
    """specs/teams-usage, "Zespół bez ustawionych granic"."""
    definition = TeamDefinition(
        agents=[an_agent("scout"), an_agent("judge")],
        edges=[TeamEdge(from_="scout", to="judge")],
    )
    provider = ScriptedProvider(default=says("done"))

    _, run_id = await _run(pool, definition, provider)

    async with pool.acquire() as conn:
        run = await store.get_run(conn, run_id=run_id, owner_principal=OWNER)
    assert run is not None
    assert run["status"] == "completed"


async def test_a_limit_that_is_not_reached_lets_the_run_finish(pool: asyncpg.Pool) -> None:
    definition = TeamDefinition(
        agents=[an_agent("scout"), an_agent("judge")],
        edges=[TeamEdge(from_="scout", to="judge")],
        limits=CostLimits(run_limit="1"),
    )

    _, run_id = await _run(pool, definition, ScriptedProvider(default=says("done")))

    async with pool.acquire() as conn:
        run = await store.get_run(conn, run_id=run_id, owner_principal=OWNER)
        rows = await conn.fetch("SELECT cost FROM usage WHERE run_id = $1", run_id)
    assert run is not None
    assert run["status"] == "completed"
    assert sum(row["cost"] for row in rows) == ONE_CALL * 2


async def test_a_price_change_does_not_move_what_earlier_rows_cost(pool: asyncpg.Pool) -> None:
    """specs/teams-usage, "Cennik zmienia się po przebiegu" — the reason the rate is copied
    onto the row and the cost is written there rather than derived at read time."""
    definition = TeamDefinition(agents=[an_agent("scout")])
    _, run_id = await _run(pool, definition, ScriptedProvider(default=says("up")))

    async with pool.acquire() as conn:
        before = await conn.fetchrow("SELECT * FROM usage WHERE run_id = $1", run_id)
        assert before is not None
        step_id = before["run_step_id"]
        # The same model, ten times dearer from now on — a rate the catalogue could carry
        # tomorrow after an operator edits `MODELS`.
        after = await store.record_usage(
            conn,
            run_id=run_id,
            run_step_id=step_id,
            model_id="gpt-5.6-luna",
            input_tokens=100,
            output_tokens=20,
            cached_tokens=None,
            reasoning_tokens=None,
            input_rate_per_1m=Decimal(10),
            output_rate_per_1m=Decimal(60),
        )
        reread = await conn.fetchrow("SELECT * FROM usage WHERE id = $1", before["id"])

    assert reread is not None
    assert reread["cost"] == before["cost"] == ONE_CALL
    assert reread["input_rate_per_1m"] == Decimal(1)
    # The new row carries the new rate — both are true at once, which is the whole point.
    assert after["cost"] == ONE_CALL * 10


async def test_todays_spend_is_what_the_daily_ceiling_reads(pool: asyncpg.Pool) -> None:
    definition = TeamDefinition(agents=[an_agent("scout")])
    team_id, _ = await _run(pool, definition, ScriptedProvider(default=says("up")))

    async with pool.acquire() as conn:
        today = await store.team_cost_since(
            conn,
            team_id=team_id,
            owner_principal=OWNER,
            since=datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0),
        )
        tomorrow = await store.team_cost_since(
            conn,
            team_id=team_id,
            owner_principal=OWNER,
            since=datetime.now(UTC) + timedelta(days=1),
        )
        # Somebody else's team spends nothing of this operator's budget.
        stranger = await store.team_cost_since(
            conn,
            team_id=team_id,
            owner_principal="operator-2",
            since=datetime.now(UTC) - timedelta(days=1),
        )

    assert today == ONE_CALL
    assert tomorrow == Decimal(0)
    assert stranger == Decimal(0)
