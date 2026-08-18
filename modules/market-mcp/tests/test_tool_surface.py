"""Task 4.6: the opinion every tool's description has to hold up, since it is the
only thing a model knows about a tool before calling it
(specs/market-mcp-tools, "Opis narzędzia jest częścią kontraktu").
"""

from __future__ import annotations

import json

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
    "list_tracked_symbols",
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


# --- the surface as a running cost (specs/market-mcp-tools, "Powierzchnia narzędzi ma zapisany sufit") ---

# Characters of the serialized `list_tools()`, which is what an MCP client reads before
# every turn. In characters rather than tokens so the test needs no tokenizer: the ratio
# measured on this material with `cl100k_base` is a steady 4,2, so the ceiling below is
# ~4 700 tokens. Raising it is a deliberate edit of this line, never a side effect of
# adding a tool — that is the whole point of writing it down.
SURFACE_CEILING_CHARS = 19700


def _surface(tools) -> str:
    return json.dumps(
        [t.model_dump(exclude_none=True) for t in tools], separators=(",", ":"), ensure_ascii=False
    )


async def test_the_surface_stays_under_its_ceiling(server) -> None:
    mcp, upstream = server
    measured = len(_surface(await mcp.list_tools()))
    assert measured <= SURFACE_CEILING_CHARS, (
        f"the tool surface is {measured} characters, above the {SURFACE_CEILING_CHARS} "
        "ceiling. Shorten a description, narrow a reply, or raise the ceiling on purpose."
    )
    await upstream.aclose()


# Maps of name -> schema, whose *keys* are field names and mean nothing here. An indicator
# parameter really is called `default`, which is why this test walks the schema instead of
# searching its text.
_NAME_MAPS = ("properties", "$defs", "patternProperties")


def _keys_at_every_level(node, inside_name_map: bool = False):
    if isinstance(node, list):
        for item in node:
            yield from _keys_at_every_level(item)
        return
    if not isinstance(node, dict):
        return
    for key, value in node.items():
        if not inside_name_map:
            yield key
        # A field genuinely named `properties` is a field name, not a nesting level.
        yield from _keys_at_every_level(value, key in _NAME_MAPS and not inside_name_map)


async def test_the_schema_carries_no_scaffolding(server) -> None:
    """The other half of the ceiling: a budget spent on `title` repeating the field's own
    name is a budget not spent on saying anything."""
    mcp, upstream = server
    for tool in await mcp.list_tools():
        assert "title" not in set(_keys_at_every_level(tool.inputSchema)), tool.name
        if tool.outputSchema is not None:
            keys = set(_keys_at_every_level(tool.outputSchema))
            assert "title" not in keys, tool.name
            assert "default" not in keys, tool.name
    await upstream.aclose()


async def test_the_schema_still_says_what_a_reply_holds(server) -> None:
    """And the half that stops the one above from being satisfied by publishing nothing."""
    mcp, upstream = server
    by_name = {t.name: t for t in await mcp.list_tools()}
    output = by_name["compute_indicators"].outputSchema
    assert output is not None
    assert output["required"]
    assert all("type" in p or "anyOf" in p or "$ref" in p for p in output["properties"].values())
    await upstream.aclose()
