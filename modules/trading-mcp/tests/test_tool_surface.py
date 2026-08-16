"""specs/trading-mcp-tools: the announced shape of the set, not what any one tool
does — read vs write annotations, and the absence of a market tool.
"""

from __future__ import annotations

READ_TOOLS = {"get_positions", "get_working_orders", "get_balance"}
WRITE_TOOLS = {"place_order", "close_position", "amend_stops", "cancel_working_order"}


async def test_the_expected_tools_and_no_others(server) -> None:
    mcp, gateway = server
    tools = await mcp.list_tools()
    assert {t.name for t in tools} == READ_TOOLS | WRITE_TOOLS
    await gateway.aclose()


async def test_read_tools_are_annotated_read_only(server) -> None:
    mcp, gateway = server
    by_name = {t.name: t for t in await mcp.list_tools()}
    for name in READ_TOOLS:
        annotations = by_name[name].annotations
        assert annotations is not None, name
        assert annotations.readOnlyHint is True, name
        assert annotations.destructiveHint is False, name
    await gateway.aclose()


async def test_write_tools_are_annotated_as_changing_state(server) -> None:
    mcp, gateway = server
    by_name = {t.name: t for t in await mcp.list_tools()}
    for name in WRITE_TOOLS:
        annotations = by_name[name].annotations
        assert annotations is not None, name
        assert annotations.readOnlyHint is False, name
        assert annotations.destructiveHint is True, name
    await gateway.aclose()


async def test_no_tool_answers_about_price_candles_or_indicators(server) -> None:
    mcp, gateway = server
    names = {t.name for t in await mcp.list_tools()}
    for market_word in ("price", "candle", "indicator"):
        assert not any(market_word in name for name in names)
    await gateway.aclose()


async def test_the_server_description_points_to_market_mcp_for_the_market(server) -> None:
    mcp, gateway = server
    assert "market-mcp" in mcp.instructions
    await gateway.aclose()


async def test_every_tool_has_a_description(server) -> None:
    mcp, gateway = server
    for tool in await mcp.list_tools():
        assert tool.description and len(tool.description.strip()) > 20, tool.name
    await gateway.aclose()
