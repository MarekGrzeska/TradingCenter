"""A team trading on an account of its own: the run puts the revision's account into every account call, the model
never sees the argument, and an account the gateway does not list stops the run before any agent."""

from __future__ import annotations

import json

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from teams.contract import AgentDefinition, TeamDefinition, TradingLimits
from teams.tools import AccountNotListed, AnnouncedSnapshot, ToolServerRegistry, plan_tools
from teams.validation import DefinitionRefused, check_definition

from .mcp_stand_in import READ_ONLY, serving, settings_for

WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=True)


def trading_stand_in(mcp: FastMCP) -> None:
    """trading-mcp's shape where it matters here: an optional `account_id`, and the accounts it lists."""

    @mcp.tool(name="place_order", annotations=WRITE)
    def place_order(symbol: str, account_id: str | None = None) -> str:
        return json.dumps({"symbol": symbol, "account_id": account_id})

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


async def _planned(definition: TeamDefinition):
    async with serving(build=trading_stand_in) as url:
        registry = ToolServerRegistry.from_settings(settings_for(url))
        try:
            plan = await plan_tools(definition, registry)
            outcome = await plan.call(
                "place_order", {"symbol": "US100", "account_id": "Y"}, agent_key="trader"
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


async def test_a_revision_without_an_account_leaves_the_call_alone() -> None:
    # specs/teams-trading, "Rewizja bez konta"
    plan, sent = await _planned(trader(None))

    assert sent["account_id"] == "Y"
    assert "account_id" in plan.for_agent("trader")[0].input_schema["properties"]
    assert plan.account_for("place_order") is None


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
