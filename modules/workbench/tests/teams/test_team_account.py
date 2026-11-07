"""A team trading on an account of its own: the run puts the revision's account into every account call, the model
never sees the argument, and an account the gateway does not list stops the run before any agent."""

from __future__ import annotations

import json

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import ValidationError

from teams.contract import AgentDefinition, TeamDefinition, TradingLimits
from teams.tools import (
    AccountMovingToolOnAnAccount,
    AccountNotListed,
    AnnouncedSnapshot,
    ToolServerRegistry,
    ToolServerUnavailable,
    plan_tools,
)
from teams.validation import DefinitionRefused, check_definition

from .mcp_stand_in import READ_ONLY, serving, settings_for

WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=True)


def trading_stand_in(mcp: FastMCP) -> None:
    """trading-mcp's shape where it matters here: an optional `account_id`, and the accounts it lists."""

    @mcp.tool(name="place_order", annotations=WRITE)
    def place_order(symbol: str, account_id: str | None = None) -> str:
        return json.dumps({"symbol": symbol, "account_id": account_id})

    @mcp.tool(name="switch_active_account", annotations=WRITE)
    def switch_active_account(account_id: str) -> str:
        return json.dumps({"account_id": account_id})

    @mcp.tool(name="list_accounts", annotations=READ_ONLY)
    def list_accounts() -> list[dict]:
        return [{"id": "X"}, {"id": "Y"}]


def trader(account_id: str | None, tools: list[str] | None = None) -> TeamDefinition:
    return TeamDefinition(
        agents=[
            AgentDefinition(
                key="trader",
                role="trades",
                prompt="trade",
                model_id="gpt-6-luna",
                tools=tools or ["place_order"],
            )
        ],
        trading=TradingLimits(account_id=account_id),
    )


async def _planned(definition: TeamDefinition, tool: str = "place_order", arguments=None):
    async with serving(build=trading_stand_in) as url:
        registry = ToolServerRegistry.from_settings(settings_for(url))
        try:
            plan = await plan_tools(definition, registry)
            outcome = await plan.call(
                tool, arguments or {"symbol": "US100", "account_id": "Y"}, agent_key="trader"
            )
        finally:
            await registry.aclose()
    return plan, json.loads(json.loads(outcome.text)["result"])


async def test_the_revisions_account_reaches_the_call_and_the_model_cannot_name_another() -> None:
    # specs/teams-trading, "Model podaje konto"
    plan, sent = await _planned(trader("X"))

    assert sent["account_id"] == "X"
    assert "account_id" not in plan.for_agent("trader")[0].input_schema["properties"]
    assert plan.account_for("place_order") == "X"


async def test_a_revision_without_an_account_trades_on_the_active_one_whatever_the_model_names() -> None:
    # specs/teams-trading, "Rewizja bez konta"
    plan, sent = await _planned(trader(None))

    assert sent["account_id"] is None
    assert "account_id" not in plan.for_agent("trader")[0].input_schema["properties"]
    assert plan.account_for("place_order") is None


async def test_the_switch_keeps_its_target_on_a_revision_without_an_account() -> None:
    plan, sent = await _planned(
        trader(None, tools=["switch_active_account"]),
        "switch_active_account",
        {"account_id": "Y"},
    )

    assert sent["account_id"] == "Y"
    assert "account_id" in plan.for_agent("trader")[0].input_schema["properties"]


async def test_a_switch_that_slipped_past_the_save_refuses_the_run() -> None:
    with pytest.raises(AccountMovingToolOnAnAccount, match="switch_active_account"):
        await _planned(trader("X", tools=["place_order", "switch_active_account"]))


async def test_an_account_the_gateway_does_not_list_refuses_the_run() -> None:
    # specs/teams-trading, "Konto rewizji przestało istnieć"
    with pytest.raises(AccountNotListed, match="gone"):
        await _planned(trader("gone"))


def test_a_team_on_its_own_account_may_not_carry_the_switch() -> None:
    # specs/teams-trading, "Rewizja z kontem i narzędziem przełączającym konto"
    definition = trader("X", tools=["place_order", "switch_active_account"])

    with pytest.raises(DefinitionRefused) as refused:
        check_definition(
            definition,
            model_ids=["gpt-6-luna"],
            announced=AnnouncedSnapshot(
                by_name={"place_order": ["trading-mcp"], "switch_active_account": ["trading-mcp"]},
                unreachable=[],
            ),
        )

    assert "trader" in str(refused.value)
    assert "switch_active_account" in str(refused.value)


def live_stand_in(mcp: FastMCP) -> None:
    """The live account's trading-mcp: the same names as the demo one, its own single account."""

    @mcp.tool(name="place_order", annotations=WRITE)
    def place_order(symbol: str, account_id: str | None = None) -> str:
        return json.dumps({"symbol": symbol, "account_id": account_id, "live": True})

    @mcp.tool(name="list_accounts", annotations=READ_ONLY)
    def list_accounts() -> list[dict]:
        return [{"id": "L1"}]


def on(environment: str, account_id: str | None) -> TeamDefinition:
    definition = trader(account_id)
    return definition.model_copy(
        update={"trading": TradingLimits(environment=environment, account_id=account_id)}  # type: ignore[arg-type]
    )


async def _with_both(definition: TeamDefinition):
    async with serving(build=trading_stand_in) as demo, serving(build=live_stand_in) as live:
        registry = ToolServerRegistry.from_settings(settings_for(demo, live_trading_mcp_url=live))
        try:
            plan = await plan_tools(definition, registry.for_environment(definition.trading.environment))
            outcome = await plan.call("place_order", {"symbol": "US100"}, agent_key="trader")
        finally:
            await registry.aclose()
    return plan, json.loads(json.loads(outcome.text)["result"])


async def test_a_live_team_trades_through_the_live_tool_server_only() -> None:
    # specs/teams-trading, "Zespół na koncie realnym idzie przez serwer narzędzi konta realnego"
    plan, sent = await _with_both(on("live", "L1"))

    assert sent == {"symbol": "US100", "account_id": "L1", "live": True}
    assert plan.environment == "live"


async def test_a_demo_team_beside_a_configured_live_server_stays_on_demo() -> None:
    plan, sent = await _with_both(on("demo", "X"))

    assert "live" not in sent
    assert plan.environment == "demo"


async def test_a_live_team_with_no_live_tool_server_is_refused_before_any_agent() -> None:
    # specs/teams-trading, "Przebieg realny bez serwera narzędzi konta realnego" — even with no tool assigned
    definition = on("live", "L1").model_copy(update={"agents": [trader("L1").agents[0].model_copy(update={"tools": []})]})
    registry = ToolServerRegistry.from_settings(settings_for(None))

    with pytest.raises(ToolServerUnavailable, match="LIVE_TRADING_MCP_URL"):
        await plan_tools(definition, registry.for_environment("live"))


def test_a_live_team_must_name_its_account() -> None:
    # specs/teams-trading, "Rewizja realna bez konta"
    with pytest.raises(ValidationError, match="account_id"):
        TradingLimits(environment="live")


def test_a_revision_from_before_the_environment_reads_as_demo() -> None:
    # specs/teams-trading, "Rewizja sprzed zmiany"
    stored = trader("X").model_dump()
    del stored["trading"]["environment"]

    assert TeamDefinition.model_validate(stored).trading.environment == "demo"
