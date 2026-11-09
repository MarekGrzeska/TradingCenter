"""What an agent beside a step leaves when it cannot answer (`teams-steps`, fallback notice), and the daily cost limit that
holds agents back while steps still run (`teams-usage`)."""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal

import asyncpg
import pytest

from teams import store
from teams.contract import (
    AgentDefinition,
    CostLimits,
    FallbackNotice,
    StepDefinition,
    TeamDefinition,
    TeamEdge,
)
from teams.models_catalogue import ModelCatalogue
from teams.runner import RunRegistry, execute_run
from teams.runner.cost import DailyCostLimitReached
from teams.runner.starter import start_run_on_revision
from teams.tools import ToolDescriptor, ToolOutcome, ToolOutcomeKind, ToolServerRegistry

from .mcp_stand_in import settings_for
from .scripted_provider import ScriptedProvider, breaks, says
from .test_strategy_execute import RecipeServer

pytestmark = pytest.mark.db

OWNER = "operator-1"
SENT = json.dumps({"delivered": True})


class DeskServer(RecipeServer):
    """The recipe's tools and the message tool, which a server that moves the account must call read-only here."""

    def __init__(self) -> None:
        super().__init__()
        self.replies["send_telegram_message"] = [ToolOutcome(ToolOutcomeKind.OK, SENT, 1)]
        self.sent: list[dict] = []

    async def list_tools(self) -> list[ToolDescriptor]:
        return [
            ToolDescriptor(name=name, description=name, input_schema={}, read_only=name not in self.WRITES)
            for name in self.replies
        ]

    async def call(self, name: str, arguments: dict) -> ToolOutcome:
        if name == "send_telegram_message":
            self.sent.append(arguments)
        return await super().call(name, arguments)


def _desk(*, daily_limit: str | None = None) -> TeamDefinition:
    return TeamDefinition(
        steps=[
            StepDefinition(
                key="execute",
                recipe="strategy_execute",
                params={"strategy_id": 5, "revision": 1, "symbol": "US100", "wait_for_bar_seconds": 0},
            )
        ],
        agents=[
            AgentDefinition(
                key="reporter",
                role="reporter",
                prompt="tell the operator",
                model_id="gpt-6-luna",
                tools=["send_telegram_message"],
                fallback_notice=FallbackNotice(destination="operator", bot="desk_bot", prefix="KONTO DEMO"),
            )
        ],
        edges=[TeamEdge(from_="execute", to="reporter")],
        limits=CostLimits(daily_limit=daily_limit),
    )


async def _run(pool: asyncpg.Pool, definition: TeamDefinition, provider, server, **extra) -> int:
    settings = settings_for(None)
    async with pool.acquire() as conn:
        team, revision = await store.create_team(
            conn, owner_principal=OWNER, name="desk", description="", definition=definition
        )
        run, _ = await store.create_run(
            conn, team_revision_id=revision["id"], owner_principal=OWNER, agent_keys=definition.node_keys()
        )
    await execute_run(
        pool,
        run_id=run["id"],
        team_id=team["id"],
        owner_principal=OWNER,
        definition=definition,
        provider=provider,
        tool_registry=ToolServerRegistry({"trading-mcp": server}),
        catalogue=ModelCatalogue.from_settings(settings),
        settings=settings,
        registry=RunRegistry(),
        **extra,
    )
    return run["id"]


async def _run_row(pool: asyncpg.Pool, run_id: int) -> asyncpg.Record:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT status, stopped_reason FROM runs WHERE id = $1", run_id)
    assert row is not None
    return row


async def test_a_reporter_whose_model_fails_leaves_the_fixed_message(pool: asyncpg.Pool) -> None:
    server = DeskServer()
    run_id = await _run(pool, _desk(), ScriptedProvider(default=breaks()), server)

    assert len(server.sent) == 1
    text = server.sent[0]["text"]
    assert text.startswith("KONTO DEMO")
    assert "US100 strategy 5/1: BUY 0.137 filled" in text
    assert "the model did not answer" in text
    assert server.sent[0]["bot"] == "desk_bot"
    row = await _run_row(pool, run_id)
    assert row["status"] == "failed"
    assert "reporter" in row["stopped_reason"]


async def test_a_notice_the_trace_cannot_record_leaves_the_model_failure_as_the_reason(
    pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorded = store.record_tool_call

    async def failing_for_the_notice(conn, **kwargs):
        if kwargs["tool_name"] == "send_telegram_message":
            raise asyncpg.PostgresConnectionError("connection lost")
        return await recorded(conn, **kwargs)

    monkeypatch.setattr(store, "record_tool_call", failing_for_the_notice)
    server = DeskServer()
    run_id = await _run(pool, _desk(), ScriptedProvider(default=breaks()), server)

    assert len(server.sent) == 1
    row = await _run_row(pool, run_id)
    assert row["status"] == "failed"
    assert "reporter" in row["stopped_reason"] and "model call failed" in row["stopped_reason"]


class SlowAccount(DeskServer):
    """An order that takes a while to come back, so an agent beside the step fails while it is in flight."""

    async def call(self, name: str, arguments: dict) -> ToolOutcome:
        if name == "place_order":
            await asyncio.sleep(0.3)
        return await super().call(name, arguments)


async def test_an_agent_failing_beside_a_step_does_not_cancel_the_order_in_flight(pool: asyncpg.Pool) -> None:
    beside = TeamDefinition(
        steps=_desk().steps,
        agents=[AgentDefinition(key="news", role="news", prompt="read the news", model_id="gpt-6-luna")],
    )

    run_id = await _run(pool, beside, ScriptedProvider(default=breaks()), SlowAccount())

    async with pool.acquire() as conn:
        trades = await store.get_run_trades(conn, run_id=run_id)
        output = await conn.fetchval(
            "SELECT output FROM run_steps WHERE run_id = $1 AND agent_key = 'execute'", run_id
        )
    assert [trade["status"] for trade in trades] == ["settled"]
    assert json.loads(output)["decision"] == "entered"
    row = await _run_row(pool, run_id)
    assert row["status"] == "failed"
    assert "news" in row["stopped_reason"]


async def test_a_reporter_that_answers_sends_no_notice(pool: asyncpg.Pool) -> None:
    server = DeskServer()
    await _run(pool, _desk(), ScriptedProvider(default=says("all good")), server)
    assert server.sent == []


async def test_with_the_daily_limit_used_up_the_step_trades_and_no_model_is_called(pool: asyncpg.Pool) -> None:
    server = DeskServer()
    provider = ScriptedProvider(default=says("never"))
    held = DailyCostLimitReached(Decimal(2), Decimal(1), steps_ran=True)

    run_id = await _run(pool, _desk(daily_limit="1"), provider, server, agents_held=held)

    assert provider.asks == []
    assert len(server.sent) == 1
    async with pool.acquire() as conn:
        trades = await store.get_run_trades(conn, run_id=run_id)
    assert [trade["status"] for trade in trades] == ["settled"]
    row = await _run_row(pool, run_id)
    assert row["status"] == "failed"
    assert "daily cost limit" in row["stopped_reason"]
    assert "steps ran" in row["stopped_reason"]


async def _spent_past(pool: asyncpg.Pool, definition: TeamDefinition) -> asyncpg.Record:
    async with pool.acquire() as conn:
        _team, revision = await store.create_team(
            conn, owner_principal=OWNER, name="desk", description="", definition=definition
        )
        run, steps = await store.create_run(
            conn, team_revision_id=revision["id"], owner_principal=OWNER, agent_keys=definition.node_keys()
        )
        await store.record_usage(
            conn,
            run_id=run["id"],
            run_step_id=steps[0]["id"],
            model_id="gpt-6-luna",
            input_tokens=1_000_000,
            output_tokens=0,
            cached_tokens=None,
            reasoning_tokens=None,
            input_rate_per_1m=Decimal(5),
            output_rate_per_1m=Decimal(5),
        )
    return revision


@pytest.mark.parametrize(("with_step", "starts"), [(True, True), (False, False)])
async def test_the_daily_limit_refuses_only_a_revision_without_steps(
    pool: asyncpg.Pool, with_step: bool, starts: bool
) -> None:
    definition = _desk(daily_limit="1")
    if not with_step:
        definition = TeamDefinition(agents=definition.agents, limits=definition.limits)
    revision = await _spent_past(pool, definition)
    settings = settings_for(None)

    async def start():
        return await start_run_on_revision(
            pool,
            revision=dict(revision),
            owner_principal=OWNER,
            catalogue=ModelCatalogue.from_settings(settings),
            provider=ScriptedProvider(default=says("never")),
            tool_registry=ToolServerRegistry({"trading-mcp": DeskServer()}),
            settings=settings,
            registry=RunRegistry(),
        )

    if starts:
        _run_record, task = await start()
        await task
    else:
        with pytest.raises(DailyCostLimitReached):
            await start()
