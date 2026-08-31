"""specs/teams-mcp-tools: the announced shape of the set, and what announcing it costs. This module publishes the most
tools of the three, so it pays for every character of scaffolding the most often — hence the ceiling below."""

from __future__ import annotations

import json

# Characters of the serialized `list_tools()`, which is what an MCP client reads before every turn — in characters
# so the test needs no tokenizer, at a measured 4.2 per token. Raising it is a deliberate edit of this line.
SURFACE_CEILING_CHARS = 21100


def _surface(tools) -> str:
    return json.dumps(
        [t.model_dump(exclude_none=True) for t in tools], separators=(",", ":"), ensure_ascii=False
    )


async def test_the_surface_stays_under_its_ceiling(server) -> None:
    mcp, _teams = server
    measured = len(_surface(await mcp.list_tools()))
    assert measured <= SURFACE_CEILING_CHARS, (
        f"the tool surface is {measured} characters, above the {SURFACE_CEILING_CHARS} "
        "ceiling. Shorten a description, narrow a reply, or raise the ceiling on purpose."
    )


# Maps of name -> schema, whose *keys* are field names and mean nothing here. An indicator parameter really is called
# `default`, which is why this test walks the schema instead of searching its text.
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
    mcp, _teams = server
    for tool in await mcp.list_tools():
        assert "title" not in set(_keys_at_every_level(tool.inputSchema)), tool.name
        if tool.outputSchema is not None:
            keys = set(_keys_at_every_level(tool.outputSchema))
            assert "title" not in keys, tool.name
            assert "default" not in keys, tool.name


async def test_the_schema_still_says_what_a_reply_holds(server) -> None:
    """And the half that stops the one above from being satisfied by publishing nothing."""
    mcp, _teams = server
    by_name = {t.name: t for t in await mcp.list_tools()}
    output = by_name["create_team"].outputSchema
    assert output is not None
    assert output["required"]
    assert all("type" in p or "anyOf" in p or "$ref" in p for p in output["properties"].values())


async def test_every_tool_has_a_description(server) -> None:
    mcp, _teams = server
    for tool in await mcp.list_tools():
        assert tool.description and len(tool.description.strip()) > 20, tool.name


async def test_every_parameter_is_typed(server) -> None:
    mcp, _teams = server
    for tool in await mcp.list_tools():
        properties = (tool.inputSchema or {}).get("properties", {})
        for param_name, schema in properties.items():
            has_type = "type" in schema or "anyOf" in schema or "$ref" in schema
            assert has_type, f"{tool.name}.{param_name} has no type in its schema"
