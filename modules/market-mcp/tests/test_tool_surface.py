"""Task 4.6: the opinion every tool's description has to hold up, since it is the
only thing a model knows about a tool before calling it
(specs/market-mcp-tools, "Opis narzędzia jest częścią kontraktu").
"""

from __future__ import annotations

# Tools whose reply is capped, and a string that must appear in their description
# naming the ceiling — not every tool has one (list_indicators/describe_indicator
# return the whole catalogue entry, uncapped by design).
CEILING_TOKENS = {
    "get_candles": ["200", "2000"],
    "describe_coverage": ["20"],
    "search_instruments": ["10"],
    "compute_indicators": ["10", "200", "20"],
    "levels_near_price": ["20"],
}

# Tools that read or return a price, and so must name which side of the spread it is.
PRICE_TOOLS = {
    "get_candles",
    "get_last_price",
    "summarize_range",
    "compute_indicators",
    "levels_near_price",
}

# Tools with a time-window parameter or a raw instant in their reply, and so must
# name the timezone.
TIME_TOOLS = {
    "get_candles",
    "get_last_price",
    "summarize_range",
    "describe_coverage",
    "compute_indicators",
    "levels_near_price",
}

EXPECTED_TOOL_NAMES = {
    "list_tracked_pairs",
    "get_candles",
    "get_last_price",
    "summarize_range",
    "describe_coverage",
    "search_instruments",
    "list_indicators",
    "describe_indicator",
    "compute_indicators",
    "levels_near_price",
}


async def test_the_expected_tools_and_no_others(server) -> None:
    mcp, upstream = server
    tools = await mcp.list_tools()
    assert {t.name for t in tools} == EXPECTED_TOOL_NAMES
    await upstream.aclose()


async def test_every_tool_has_a_description(server) -> None:
    mcp, upstream = server
    for tool in await mcp.list_tools():
        assert tool.description and len(tool.description.strip()) > 20, tool.name
    await upstream.aclose()


async def test_every_parameter_is_typed(server) -> None:
    mcp, upstream = server
    for tool in await mcp.list_tools():
        properties = (tool.inputSchema or {}).get("properties", {})
        for param_name, schema in properties.items():
            has_type = "type" in schema or "anyOf" in schema or "$ref" in schema
            assert has_type, f"{tool.name}.{param_name} has no type in its schema"
    await upstream.aclose()


async def test_every_tool_is_marked_read_only(server) -> None:
    """The structural claim, not just the convention — an MCP client can act on
    `readOnlyHint` without reading a single line of this module's source."""
    mcp, upstream = server
    for tool in await mcp.list_tools():
        assert tool.annotations is not None, tool.name
        assert tool.annotations.readOnlyHint is True, tool.name
        assert tool.annotations.destructiveHint is False, tool.name
    await upstream.aclose()


async def test_every_ceiling_is_named_in_the_description(server) -> None:
    mcp, upstream = server
    by_name = {t.name: t for t in await mcp.list_tools()}
    for name, tokens in CEILING_TOKENS.items():
        description = by_name[name].description or ""
        for token in tokens:
            assert token in description, f"{name} does not name its {token} ceiling"
    await upstream.aclose()


async def test_price_tools_name_which_side_of_the_spread(server) -> None:
    mcp, upstream = server
    by_name = {t.name: t for t in await mcp.list_tools()}
    for name in PRICE_TOOLS:
        description = (by_name[name].description or "").lower()
        assert "bid" in description, f"{name} does not name the bid side"
    await upstream.aclose()


async def test_time_tools_name_the_timezone(server) -> None:
    mcp, upstream = server
    by_name = {t.name: t for t in await mcp.list_tools()}
    for name in TIME_TOOLS:
        description = by_name[name].description or ""
        assert "UTC" in description, f"{name} does not name the timezone"
    await upstream.aclose()
