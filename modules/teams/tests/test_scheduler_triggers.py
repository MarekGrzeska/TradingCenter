"""The clock evaluating triggers — `scheduler/clock.py` against a real database, a
scripted model, and a real MCP stand-in whose numeric answer a test can move between
calls (`_register_value_tool` below) — not a mock, for the same reason
`test_catalogue_tools.py` uses a real server: the one contract with no committed
snapshot is this session.

`_check_trigger` (module-private) is used directly only where a test needs to await the
failure-streak bookkeeping deterministically — see `test_scheduler_clock.py`'s own
docstring for why that is the one place reaching past `Clock.tick()` is warranted.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import asyncpg
import pytest
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel

from teams import store
from teams.contract import AgentDefinition, TeamDefinition
from teams.models_catalogue import ModelCatalogue
from teams.runner import RunRegistry
from teams.scheduler.clock import Clock, _check_trigger
from teams.tools import ToolServerRegistry

from .mcp_stand_in import serving, settings_for
from .scripted_provider import ScriptedProvider, breaks, says

pytestmark = pytest.mark.db

OWNER = "operator-1"
MODEL_ID = "gpt-5.6-luna"
PAST = datetime.now(UTC) - timedelta(minutes=1)


class _ValueOut(BaseModel):
    value: float


def _register_value_tool(mcp: FastMCP, box: list[float]) -> None:
    """A tool whose answer a test moves between calls — `box` is shared by reference,
    the way an operator's own instrument would move between two checks."""

    @mcp.tool(name="read_value", description="A controllable numeric reading, for testing triggers.")
    def read_value() -> _ValueOut:
        return _ValueOut(value=box[0])


def _register_refusing_tool(mcp: FastMCP) -> None:
    @mcp.tool(name="always_refuses", description="Always refuses, for testing.")
    def always_refuses() -> str:
        raise ValueError("nope, not shaped like that")


def _definition() -> TeamDefinition:
    return TeamDefinition(
        agents=[AgentDefinition(key="scout", role="scout", prompt="read the market", model_id=MODEL_ID)]
    )


async def _team_and_revision(pool: asyncpg.Pool) -> tuple[int, int]:
    async with pool.acquire() as conn:
        team, revision = await store.create_team(
            conn, owner_principal=OWNER, name="morning desk", description="", definition=_definition()
        )
    return team["id"], revision["id"]


async def _trigger(
    pool: asyncpg.Pool,
    *,
    team_id: int,
    revision_id: int,
    threshold: str = "70",
    comparison: str = "gt",
    cooldown_seconds: int = 900,
    tool_name: str = "read_value",
    field_path: str = "value",
) -> asyncpg.Record:
    async with pool.acquire() as conn:
        return await store.create_trigger(
            conn,
            team_id=team_id,
            owner_principal=OWNER,
            revision_mode="pinned",
            pinned_revision_id=revision_id,
            tool_name=tool_name,
            arguments={},
            field_path=field_path,
            comparison=comparison,
            threshold=Decimal(threshold),
            cooldown_seconds=cooldown_seconds,
            poll_interval_seconds=300,
            next_check_at=PAST,
            unattended_ack=False,
        )


def _clock(pool: asyncpg.Pool, *, provider, settings) -> Clock:
    return Clock(
        pool,
        catalogue=ModelCatalogue.from_settings(settings),
        provider=provider,
        tool_registry=ToolServerRegistry.from_settings(settings),
        settings=settings,
        registry=RunRegistry(),
    )


async def _fires(pool: asyncpg.Pool, *, trigger_id: int) -> list[asyncpg.Record]:
    async with pool.acquire() as conn:
        return await store.list_fires_for_trigger(conn, trigger_id=trigger_id, owner_principal=OWNER)


async def _make_due_again(pool: asyncpg.Pool, trigger_id: int, *, clear_cooldown: bool = False) -> None:
    """`claim_trigger_for_check` already moved `next_check_at` forward — this is a test
    standing in for time actually passing, not something a route or the clock offers."""
    async with pool.acquire() as conn:
        if clear_cooldown:
            await conn.execute(
                "UPDATE triggers SET next_check_at = $1, last_fired_at = NULL WHERE id = $2", PAST, trigger_id
            )
        else:
            await conn.execute("UPDATE triggers SET next_check_at = $1 WHERE id = $2", PAST, trigger_id)


async def test_a_condition_below_threshold_does_not_fire_or_cost_tokens(pool: asyncpg.Pool) -> None:
    box = [50.0]
    async with serving(build=lambda mcp: _register_value_tool(mcp, box)) as url:
        settings = settings_for(url)
        team_id, revision_id = await _team_and_revision(pool)
        trigger = await _trigger(pool, team_id=team_id, revision_id=revision_id, threshold="70")

        clock = _clock(pool, provider=ScriptedProvider(default=says("done")), settings=settings)
        await clock.tick()

    assert await _fires(pool, trigger_id=trigger["id"]) == []
    async with pool.acquire() as conn:
        row = await store.get_trigger(conn, trigger_id=trigger["id"], owner_principal=OWNER)
        usage_rows = await conn.fetchval("SELECT count(*) FROM usage")
    assert row is not None
    assert row["last_result"] is False
    # specs/teams-triggers, "Obserwowanie rynku nie kosztuje tokenów modelu".
    assert usage_rows == 0


async def test_a_condition_crossing_the_threshold_fires_exactly_once(pool: asyncpg.Pool) -> None:
    box = [50.0]
    async with serving(build=lambda mcp: _register_value_tool(mcp, box)) as url:
        settings = settings_for(url)
        team_id, revision_id = await _team_and_revision(pool)
        trigger = await _trigger(pool, team_id=team_id, revision_id=revision_id, threshold="70")
        clock = _clock(pool, provider=ScriptedProvider(default=says("the trend is up")), settings=settings)

        await clock.tick()
        assert await _fires(pool, trigger_id=trigger["id"]) == []

        box[0] = 80.0
        await _make_due_again(pool, trigger["id"])
        # `gather`-ed rather than left detached: `tick()` hands back the failure-streak
        # tasks so a test can know every write this wake will make has happened before
        # the `pool` fixture tears down underneath a still-running one.
        await asyncio.gather(*await clock.tick())

        fires = await _fires(pool, trigger_id=trigger["id"])
        assert len(fires) == 1
        assert fires[0]["outcome"] == "started"
        assert fires[0]["run_id"] is not None

        # Still true on the next check — specs/teams-triggers, "Warunek spełniony i
        # pozostający spełniony": exactly one fire, not a second one.
        await _make_due_again(pool, trigger["id"])
        await clock.tick()

        assert len(await _fires(pool, trigger_id=trigger["id"])) == 1


async def test_a_flapping_condition_within_cooldown_is_suppressed(pool: asyncpg.Pool) -> None:
    box = [80.0]
    async with serving(build=lambda mcp: _register_value_tool(mcp, box)) as url:
        settings = settings_for(url)
        team_id, revision_id = await _team_and_revision(pool)
        trigger = await _trigger(
            pool, team_id=team_id, revision_id=revision_id, threshold="70", cooldown_seconds=900
        )
        clock = _clock(pool, provider=ScriptedProvider(default=says("done")), settings=settings)

        await asyncio.gather(*await clock.tick())
        first_fires = await _fires(pool, trigger_id=trigger["id"])
        assert len(first_fires) == 1

        box[0] = 50.0
        await _make_due_again(pool, trigger["id"])
        await clock.tick()  # drops below — resets the edge, no fire either way

        box[0] = 90.0
        await _make_due_again(pool, trigger["id"])
        await clock.tick()  # crosses again, well inside the 900s cooldown

        fires = await _fires(pool, trigger_id=trigger["id"])
        assert len(fires) == 2
        newest = fires[0]
        assert newest["outcome"] == "skipped"
        assert "cooldown" in newest["reason"]
        assert newest["run_id"] is None


async def test_a_trigger_with_no_tool_server_is_recorded_as_unavailable_not_false(pool: asyncpg.Pool) -> None:
    settings = settings_for(None)
    team_id, revision_id = await _team_and_revision(pool)
    trigger = await _trigger(pool, team_id=team_id, revision_id=revision_id)
    clock = _clock(pool, provider=ScriptedProvider(default=says("done")), settings=settings)

    await clock.tick()

    fires = await _fires(pool, trigger_id=trigger["id"])
    assert len(fires) == 1
    assert fires[0]["outcome"] == "unavailable"
    assert fires[0]["run_id"] is None
    async with pool.acquire() as conn:
        row = await store.get_trigger(conn, trigger_id=trigger["id"], owner_principal=OWNER)
    assert row is not None
    # `None`, not `False` — specs/teams-triggers, "Niedostępność serwera narzędzi to nie
    # jest niespełniony warunek".
    assert row["last_result"] is None


async def test_a_refused_tool_call_is_recorded_with_its_own_reason(pool: asyncpg.Pool) -> None:
    async with serving(build=_register_refusing_tool) as url:
        settings = settings_for(url)
        team_id, revision_id = await _team_and_revision(pool)
        trigger = await _trigger(
            pool, team_id=team_id, revision_id=revision_id, tool_name="always_refuses", field_path="value"
        )
        clock = _clock(pool, provider=ScriptedProvider(default=says("done")), settings=settings)

        await clock.tick()

        fires = await _fires(pool, trigger_id=trigger["id"])
    assert len(fires) == 1
    assert fires[0]["outcome"] == "unavailable"
    assert "refused" in fires[0]["reason"]


async def test_a_previous_trigger_run_still_working_is_skipped(pool: asyncpg.Pool) -> None:
    box = [80.0]
    async with serving(build=lambda mcp: _register_value_tool(mcp, box)) as url:
        settings = settings_for(url)
        team_id, revision_id = await _team_and_revision(pool)
        trigger = await _trigger(pool, team_id=team_id, revision_id=revision_id, threshold="70")

        async with pool.acquire() as conn:
            stuck_run, _ = await store.create_run(
                conn, team_revision_id=revision_id, owner_principal=OWNER, agent_keys=["scout"]
            )
            await store.record_fire(conn, trigger_id=trigger["id"], outcome="started", run_id=stuck_run["id"])

        clock = _clock(pool, provider=ScriptedProvider(default=says("done")), settings=settings)
        await clock.tick()

        fires = await _fires(pool, trigger_id=trigger["id"])
    assert len(fires) == 2
    newest = fires[0]
    assert newest["outcome"] == "skipped"
    assert "still working" in newest["reason"]


async def _check_directly(pool: asyncpg.Pool, trigger_id: int, *, provider, settings) -> None:
    async with pool.acquire() as conn:
        row = await store.get_trigger(conn, trigger_id=trigger_id, owner_principal=OWNER)
    assert row is not None
    # Closed when this helper is done, the way `app.py`'s lifespan closes the one it
    # builds. A registry left open holds an MCP session that outlives the task it was
    # opened in, and anyio reports that as "attempted to exit cancel scope in a different
    # task" somewhere entirely unrelated (`tools/client.py`'s own note on the trap).
    tools = ToolServerRegistry.from_settings(settings)
    try:
        task = await _check_trigger(
            pool,
            dict(row),
            catalogue=ModelCatalogue.from_settings(settings),
            provider=provider,
            tool_registry=tools,
            settings=settings,
            registry=RunRegistry(),
        )
        assert task is not None
        await task
    finally:
        await tools.aclose()


async def test_three_consecutive_failed_runs_disable_the_trigger(pool: asyncpg.Pool) -> None:
    box = [80.0]
    async with serving(build=lambda mcp: _register_value_tool(mcp, box)) as url:
        settings = settings_for(url, scheduler_failure_threshold=3)
        team_id, revision_id = await _team_and_revision(pool)
        trigger = await _trigger(pool, team_id=team_id, revision_id=revision_id, threshold="70")

        for _ in range(3):
            # A fresh false->true edge each time, cooldown cleared — this test is about
            # the failure streak, not about re-proving the edge/cooldown logic above.
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE triggers SET last_result = false, last_fired_at = NULL, next_check_at = $1 "
                    "WHERE id = $2",
                    PAST,
                    trigger["id"],
                )
            await _check_directly(
                pool, trigger["id"], provider=ScriptedProvider(default=breaks("provider is down")), settings=settings
            )

        async with pool.acquire() as conn:
            disabled = await store.get_trigger(conn, trigger_id=trigger["id"], owner_principal=OWNER)
    assert disabled is not None
    assert disabled["enabled"] is False
    assert "3" in disabled["disabled_reason"]


async def test_a_completed_trigger_run_resets_the_failure_streak(pool: asyncpg.Pool) -> None:
    box = [80.0]
    async with serving(build=lambda mcp: _register_value_tool(mcp, box)) as url:
        settings = settings_for(url)
        team_id, revision_id = await _team_and_revision(pool)
        trigger = await _trigger(pool, team_id=team_id, revision_id=revision_id, threshold="70")

        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE triggers SET last_result = false, next_check_at = $1 WHERE id = $2", PAST, trigger["id"]
            )
        await _check_directly(
            pool, trigger["id"], provider=ScriptedProvider(default=breaks("provider is down")), settings=settings
        )
        async with pool.acquire() as conn:
            after_failure = await store.get_trigger(conn, trigger_id=trigger["id"], owner_principal=OWNER)
        assert after_failure is not None
        assert after_failure["consecutive_failures"] == 1

        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE triggers SET last_result = false, last_fired_at = NULL, next_check_at = $1 WHERE id = $2",
                PAST,
                trigger["id"],
            )
        await _check_directly(pool, trigger["id"], provider=ScriptedProvider(default=says("done")), settings=settings)

        async with pool.acquire() as conn:
            after_success = await store.get_trigger(conn, trigger_id=trigger["id"], owner_principal=OWNER)
    assert after_success is not None
    assert after_success["consecutive_failures"] == 0
    assert after_success["enabled"] is True
