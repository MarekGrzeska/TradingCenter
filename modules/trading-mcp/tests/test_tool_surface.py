"""specs/trading-mcp-tools: the announced shape of the set — read vs write annotations, the absence of
a market tool, and what the whole set costs to read."""

from __future__ import annotations

import json

READ_TOOLS = {
    "get_positions",
    "get_working_orders",
    "get_balance",
    "get_instrument_terms",
    "size_for_margin",
    "list_accounts",
}
# Choosing the account and funding it change what money is at stake as surely as placing
# an order does (specs/trading-mcp-tools, "Zmianą stanu jest także wybór rachunku").
WRITE_TOOLS = {
    "place_order",
    "close_position",
    "amend_stops",
    "cancel_working_order",
    "switch_active_account",
    "top_up_demo_account",
}


async def test_the_expected_tools_and_no_others(server) -> None:
    mcp = server
    tools = await mcp.list_tools()
    assert {t.name for t in tools} == READ_TOOLS | WRITE_TOOLS


async def test_read_tools_are_annotated_read_only(server) -> None:
    mcp = server
    by_name = {t.name: t for t in await mcp.list_tools()}
    for name in READ_TOOLS:
        annotations = by_name[name].annotations
        assert annotations is not None, name
        assert annotations.readOnlyHint is True, name
        assert annotations.destructiveHint is False, name


async def test_write_tools_are_annotated_as_changing_state(server) -> None:
    mcp = server
    by_name = {t.name: t for t in await mcp.list_tools()}
    for name in WRITE_TOOLS:
        annotations = by_name[name].annotations
        assert annotations is not None, name
        assert annotations.readOnlyHint is False, name
        assert annotations.destructiveHint is True, name


async def test_no_tool_answers_about_price_candles_or_indicators(server) -> None:
    mcp = server
    names = {t.name for t in await mcp.list_tools()}
    for market_word in ("price", "candle", "indicator"):
        assert not any(market_word in name for name in names)


async def test_the_server_description_points_to_market_mcp_for_the_market(server) -> None:
    mcp = server
    assert "market-mcp" in mcp.instructions


async def test_every_tool_has_a_description(server) -> None:
    mcp = server
    for tool in await mcp.list_tools():
        assert tool.description and len(tool.description.strip()) > 20, tool.name


# Maps of name -> schema, whose *keys* are field names and mean nothing here. An indicator parameter
# really is called `default`, which is why this test walks the schema instead of searching its text.
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
    """`list_tools()` is read before every turn, so a budget spent on `title` repeating
    the field's own name is a budget not spent on saying anything."""
    mcp = server
    for tool in await mcp.list_tools():
        assert "title" not in set(_keys_at_every_level(tool.inputSchema)), tool.name
        if tool.outputSchema is not None:
            keys = set(_keys_at_every_level(tool.outputSchema))
            assert "title" not in keys, tool.name
            assert "default" not in keys, tool.name


async def test_the_schema_still_says_what_a_reply_holds(server) -> None:
    """And the half that stops the one above from being satisfied by publishing nothing."""
    mcp = server
    by_name = {t.name: t for t in await mcp.list_tools()}
    output = by_name["place_order"].outputSchema
    assert output is not None
    assert output["required"]
    assert all("type" in p or "anyOf" in p or "$ref" in p for p in output["properties"].values())


async def test_a_tool_taking_a_size_says_what_a_size_is(server) -> None:
    """The unit a model has to guess is the one that changes how much money moves: `size` read as lots
    rather than as units of the instrument is a different order, placed without an error."""
    mcp = server
    for tool in await mcp.list_tools():
        properties = (tool.inputSchema or {}).get("properties", {})
        if "size" not in properties:
            continue
        description = tool.description or ""
        assert "unit" in description.lower(), tool.name
        assert "size_for_margin" in description or tool.name == "size_for_margin", tool.name


SURFACE_CEILING_CHARS = 15_000

# Measured 13 772 characters on 20 August 2026 across twelve tools. The headroom is about a tenth:
# one more tool of that size fits, a paragraph added to every description does not.


def _surface(tools) -> str:
    return json.dumps(
        [t.model_dump(exclude_none=True) for t in tools], separators=(",", ":"), ensure_ascii=False
    )


async def test_the_surface_stays_under_its_ceiling(server) -> None:
    """Read by the model in every turn of a conversation that holds these tools, so its
    size is a cost paid per turn, not an implementation detail."""
    measured = len(_surface(await server.list_tools()))
    assert measured <= SURFACE_CEILING_CHARS, (
        f"the tool surface is {measured} characters, above the {SURFACE_CEILING_CHARS} "
        "ceiling. Shorten a description, narrow a reply, or raise the ceiling on purpose."
    )
