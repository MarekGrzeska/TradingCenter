"""A whole run against a real database: what it writes while it works, and what it leaves
behind however it ended."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import asyncpg
import pytest

from teams import store
from teams.contract import AgentDefinition, TeamDefinition, TeamEdge
from teams.models_catalogue import ModelCatalogue
from teams.provider import ProviderChunk, TextDelta, UsageReport
from teams.runner import RunRegistry, StepFinished, StepStarted, ToolCalled, execute_run
from teams.tools import ToolDescriptor, ToolServer

from .mcp_stand_in import settings_for
from .scripted_provider import ScriptedProvider, asks_for_tool, breaks, says

pytestmark = pytest.mark.db

OWNER = "operator-1"


def an_agent(key: str, *, tools: list[str] | None = None) -> AgentDefinition:
    return AgentDefinition(
        key=key, role=key, prompt=f"be the {key}", model_id="gpt-5.6-luna", tools=tools or []
    )


async def _team(pool: asyncpg.Pool, definition: TeamDefinition) -> tuple[int, int]:
    async with pool.acquire() as conn:
        team, revision = await store.create_team(
            conn,
            owner_principal=OWNER,
            name="a team",
            description="",
            definition=definition,
        )
    return team["id"], revision["id"]


async def _run_it(
    pool: asyncpg.Pool,
    definition: TeamDefinition,
    *,
    provider,
    tool_server: ToolServer | None = None,
    timeout: float = 30.0,
    registry: RunRegistry | None = None,
) -> int:
    _, revision_id = await _team(pool, definition)
    async with pool.acquire() as conn:
        run, _ = await store.create_run(
            conn,
            team_revision_id=revision_id,
            owner_principal=OWNER,
            agent_keys=[agent.key for agent in definition.agents],
        )
    settings = settings_for(None, run_timeout_seconds=timeout)
    await execute_run(
        pool,
        run_id=run["id"],
        definition=definition,
        provider=provider,
        tool_server=tool_server or ToolServer(settings),
        catalogue=ModelCatalogue.from_settings(settings),
        settings=settings,
        registry=registry or RunRegistry(),
    )
    return run["id"]


async def _trace(pool: asyncpg.Pool, run_id: int) -> tuple[dict, list[dict], list[dict], list[dict]]:
    async with pool.acquire() as conn:
        run = await store.get_run(conn, run_id=run_id, owner_principal=OWNER)
        steps = await store.get_run_steps(conn, run_id=run_id)
        calls = await store.get_run_tool_calls(conn, run_id=run_id)
        usage = await conn.fetch("SELECT * FROM usage WHERE run_id = $1 ORDER BY id", run_id)
    assert run is not None
    return dict(run), [dict(row) for row in steps], [dict(row) for row in calls], [dict(row) for row in usage]


async def test_a_finished_run_carries_every_agents_work(pool: asyncpg.Pool) -> None:
    definition = TeamDefinition(
        agents=[an_agent("scout"), an_agent("judge")],
        edges=[TeamEdge(from_="scout", to="judge")],
    )
    provider = ScriptedProvider(
        by_role={"scout": says("the trend is up"), "judge": says("go long, small")}
    )

    run_id = await _run_it(pool, definition, provider=provider)
    run, steps, calls, usage = await _trace(pool, run_id)

    assert run["status"] == "completed"
    assert run["stopped_reason"] is None
    assert run["finished_at"] is not None
    assert {step["agent_key"]: step["status"] for step in steps} == {
        "scout": "completed",
        "judge": "completed",
    }
    assert {step["agent_key"]: step["output"] for step in steps} == {
        "scout": "the trend is up",
        "judge": "go long, small",
    }
    assert calls == []
    # One usage row per model call, priced at write time (specs/teams-usage).
    assert len(usage) == 2
    assert all(row["cost"] is not None for row in usage)
    assert all(row["model_id"] == "gpt-5.6-luna" for row in usage)


async def test_the_judge_is_briefed_with_what_the_scout_said(pool: asyncpg.Pool) -> None:
    definition = TeamDefinition(
        agents=[an_agent("scout"), an_agent("judge")],
        edges=[TeamEdge(from_="scout", to="judge")],
    )
    provider = ScriptedProvider(
        by_role={"scout": says("US100 broke its range"), "judge": says("agreed")}
    )

    await _run_it(pool, definition, provider=provider)

    judge_ask = provider.asks_for("judge")[0]
    assert "US100 broke its range" in judge_ask.briefing


async def test_a_broken_agent_fails_the_run_and_keeps_what_came_before(
    pool: asyncpg.Pool,
) -> None:
    """specs/teams-runs, "Przebieg kończy się błędem w połowie"."""
    definition = TeamDefinition(
        agents=[an_agent("scout"), an_agent("judge")],
        edges=[TeamEdge(from_="scout", to="judge")],
    )
    provider = ScriptedProvider(
        by_role={"scout": says("the trend is up"), "judge": breaks("provider is down")}
    )

    run_id = await _run_it(pool, definition, provider=provider)
    run, steps, _, usage = await _trace(pool, run_id)

    assert run["status"] == "failed"
    assert "judge" in run["stopped_reason"]
    by_key = {step["agent_key"]: step for step in steps}
    assert by_key["scout"]["status"] == "completed"
    assert by_key["scout"]["output"] == "the trend is up"
    assert by_key["judge"]["status"] == "failed"
    # The failed agent was still billed for the call it made — with no tokens, because the
    # provider never reported any (specs/teams-usage, "Brak informacji o zużyciu").
    judge_usage = [row for row in usage if row["run_step_id"] == by_key["judge"]["id"]]
    assert len(judge_usage) == 1
    assert judge_usage[0]["input_tokens"] is None
    assert judge_usage[0]["cost"] is None


async def test_a_tool_call_is_written_as_it_resolves(pool: asyncpg.Pool) -> None:
    definition = TeamDefinition(agents=[an_agent("scout", tools=["get_last_price"])])
    provider = ScriptedProvider(
        default=asks_for_tool("get_last_price", {"symbol": "US100"}, then="it is 21000.5")
    )

    class OneTool(ToolServer):
        """A tool server that answers without a session — the session itself is
        `test_tool_server.py`'s subject, not this file's."""

        def __init__(self) -> None:
            super().__init__(settings_for(None))

        async def list_tools(self) -> list[ToolDescriptor]:
            return [
                ToolDescriptor(
                    name="get_last_price", description="the last price", input_schema={}
                )
            ]

        async def call(self, name: str, arguments: dict):
            from teams.tools import ToolOutcome, ToolOutcomeKind

            del name, arguments
            return ToolOutcome(ToolOutcomeKind.OK, "21000.5", 7)

    run_id = await _run_it(pool, definition, provider=provider, tool_server=OneTool())
    run, steps, calls, usage = await _trace(pool, run_id)

    assert run["status"] == "completed"
    assert steps[0]["rounds"] == 1
    assert len(calls) == 1
    assert calls[0]["tool_name"] == "get_last_price"
    assert calls[0]["outcome"] == "ok"
    assert calls[0]["duration_ms"] == 7
    assert len(usage) == 2  # the call that asked, and the call that answered


async def test_a_team_needing_tools_without_a_server_is_refused_before_any_agent_runs(
    pool: asyncpg.Pool,
) -> None:
    """specs/teams-tool-access, "Brak serwera narzędzi zatrzymuje przebieg"."""
    definition = TeamDefinition(agents=[an_agent("scout", tools=["get_last_price"])])
    provider = ScriptedProvider(default=says("never called"))

    run_id = await _run_it(pool, definition, provider=provider)
    run, steps, _, usage = await _trace(pool, run_id)

    assert run["status"] == "failed"
    assert "tool access" in run["stopped_reason"]
    assert steps[0]["status"] == "pending"
    assert provider.asks == []
    assert usage == []


class _Sleeper:
    """A provider whose call never finishes in time — for the time limit and the
    interruption, both of which have to reach a run that is mid-model-call."""

    def __init__(self, seconds: float = 30.0) -> None:
        self.seconds = seconds
        self.entered = asyncio.Event()

    def stream(self, **kwargs) -> AsyncIterator[ProviderChunk]:
        del kwargs

        async def chunks() -> AsyncIterator[ProviderChunk]:
            self.entered.set()
            await asyncio.sleep(self.seconds)
            yield TextDelta("never")  # pragma: no cover - the sleep is never outlived
            yield UsageReport(None, None, None, None)  # pragma: no cover

        return chunks()


async def test_a_run_past_its_time_limit_is_stopped_naming_the_time(
    pool: asyncpg.Pool,
) -> None:
    """specs/teams-runs, "Przebieg przekracza dozwolony czas"."""
    definition = TeamDefinition(agents=[an_agent("scout")])

    run_id = await _run_it(pool, definition, provider=_Sleeper(), timeout=0.25)
    run, steps, _, _ = await _trace(pool, run_id)

    assert run["status"] == "failed"
    assert "time limit" in run["stopped_reason"]
    # The agent that was working when time ran out is closed, not left claiming to work.
    assert steps[0]["status"] == "failed"
    assert steps[0]["finished_at"] is not None


async def test_an_interrupted_run_keeps_the_work_that_finished(pool: asyncpg.Pool) -> None:
    """specs/teams-runs, "Operator przerywa przebieg w trakcie"."""
    definition = TeamDefinition(
        agents=[an_agent("scout"), an_agent("judge")],
        edges=[TeamEdge(from_="scout", to="judge")],
    )
    sleeper = _Sleeper()

    class TwoScripts:
        """The scout answers; the judge sleeps until it is interrupted."""

        def stream(self, *, system_prompt: str, **kwargs):
            if "You are the scout" in system_prompt:
                return ScriptedProvider(default=says("the trend is up")).stream(
                    system_prompt=system_prompt, **kwargs
                )
            return sleeper.stream(system_prompt=system_prompt, **kwargs)

    _, revision_id = await _team(pool, definition)
    async with pool.acquire() as conn:
        run, _ = await store.create_run(
            conn,
            team_revision_id=revision_id,
            owner_principal=OWNER,
            agent_keys=["scout", "judge"],
        )
    settings = settings_for(None)
    registry = RunRegistry()
    task = asyncio.create_task(
        execute_run(
            pool,
            run_id=run["id"],
            definition=definition,
            provider=TwoScripts(),
            tool_server=ToolServer(settings),
            catalogue=ModelCatalogue.from_settings(settings),
            settings=settings,
            registry=registry,
        )
    )
    registry.register(run["id"], task)

    async with asyncio.timeout(10):
        await sleeper.entered.wait()
    assert registry.cancel(run["id"]) is True
    with pytest.raises(asyncio.CancelledError):
        await task

    run_row, steps, _, _ = await _trace(pool, run["id"])
    assert run_row["status"] == "cancelled"
    assert "interrupted" in run_row["stopped_reason"]
    by_key = {step["agent_key"]: step for step in steps}
    assert by_key["scout"]["status"] == "completed"
    assert by_key["scout"]["output"] == "the trend is up"
    assert by_key["judge"]["status"] == "failed"


async def test_a_watcher_sees_the_run_as_it_happens(pool: asyncpg.Pool) -> None:
    """specs/teams-runs, "Postęp przebiegu widać w trakcie, a nie dopiero po nim"."""
    definition = TeamDefinition(
        agents=[an_agent("scout"), an_agent("judge")],
        edges=[TeamEdge(from_="scout", to="judge")],
    )
    provider = ScriptedProvider(by_role={"scout": says("up"), "judge": says("long")})
    registry = RunRegistry()

    _, revision_id = await _team(pool, definition)
    async with pool.acquire() as conn:
        run, _ = await store.create_run(
            conn,
            team_revision_id=revision_id,
            owner_principal=OWNER,
            agent_keys=["scout", "judge"],
        )
    queue = registry.subscribe(run["id"])
    settings = settings_for(None)
    await execute_run(
        pool,
        run_id=run["id"],
        definition=definition,
        provider=provider,
        tool_server=ToolServer(settings),
        catalogue=ModelCatalogue.from_settings(settings),
        settings=settings,
        registry=registry,
    )

    events = []
    while not queue.empty():
        events.append(queue.get_nowait())

    kinds = [type(event).__name__ for event in events]
    assert kinds[0] == "StepStarted"
    assert "RunFinished" in kinds
    assert events[-1] is None  # the end of the stream, so a watcher can close
    started = [event.agent_key for event in events if isinstance(event, StepStarted)]
    finished = [event.agent_key for event in events if isinstance(event, StepFinished)]
    assert started == ["scout", "judge"]
    assert finished == ["scout", "judge"]
    assert not [event for event in events if isinstance(event, ToolCalled)]


async def test_a_watcher_that_goes_away_does_not_stop_the_run(pool: asyncpg.Pool) -> None:
    definition = TeamDefinition(agents=[an_agent("scout")])
    provider = ScriptedProvider(default=says("up"))
    registry = RunRegistry()

    _, revision_id = await _team(pool, definition)
    async with pool.acquire() as conn:
        run, _ = await store.create_run(
            conn, team_revision_id=revision_id, owner_principal=OWNER, agent_keys=["scout"]
        )
    queue = registry.subscribe(run["id"])
    registry.unsubscribe(run["id"], queue)

    settings = settings_for(None)
    await execute_run(
        pool,
        run_id=run["id"],
        definition=definition,
        provider=provider,
        tool_server=ToolServer(settings),
        catalogue=ModelCatalogue.from_settings(settings),
        settings=settings,
        registry=registry,
    )

    run_row, steps, _, _ = await _trace(pool, run["id"])
    assert run_row["status"] == "completed"
    assert steps[0]["output"] == "up"


async def test_runs_left_open_by_a_dead_process_are_closed(pool: asyncpg.Pool) -> None:
    """specs/teams-runs — the start-up half of "a run lives in the process that started
    it". Without this a run whose process died reads as work in progress for ever."""
    definition = TeamDefinition(agents=[an_agent("scout"), an_agent("judge")])
    _, revision_id = await _team(pool, definition)
    async with pool.acquire() as conn:
        run, _ = await store.create_run(
            conn,
            team_revision_id=revision_id,
            owner_principal=OWNER,
            agent_keys=["scout", "judge"],
        )
        await store.mark_run_running(conn, run_id=run["id"])
        await store.start_step(conn, run_id=run["id"], agent_key="scout")

        closed = await store.fail_unfinished_runs(conn, reason="the module restarted")

    assert closed == [run["id"]]
    run_row, steps, _, _ = await _trace(pool, run["id"])
    assert run_row["status"] == "failed"
    assert "restarted" in run_row["stopped_reason"]
    assert {step["status"] for step in steps} == {"failed"}


async def test_two_agents_of_one_run_can_work_at_the_same_time(pool: asyncpg.Pool) -> None:
    """The engine's own half of `test_run_graph`'s parallelism: both agents are in the
    database as `running` at the same moment, which a sequential engine could not do."""
    definition = TeamDefinition(
        agents=[an_agent("left"), an_agent("right"), an_agent("judge")],
        edges=[TeamEdge(from_="left", to="judge"), TeamEdge(from_="right", to="judge")],
    )
    both_started = asyncio.Barrier(2)
    seen_together: list[int] = []

    class Waiter:
        def stream(self, *, system_prompt: str, **kwargs):
            del kwargs

            async def chunks() -> AsyncIterator[ProviderChunk]:
                if "You are the judge" not in system_prompt:
                    async with asyncio.timeout(10):
                        await both_started.wait()
                    async with pool.acquire() as conn:
                        running = await conn.fetchval(
                            "SELECT count(*) FROM run_steps WHERE status = 'running'"
                        )
                    seen_together.append(running)
                yield TextDelta("done")
                yield UsageReport(1, 1, None, None)

            return chunks()

    run_id = await _run_it(pool, definition, provider=Waiter())
    run, _, _, _ = await _trace(pool, run_id)

    assert run["status"] == "completed"
    assert max(seen_together) == 2
