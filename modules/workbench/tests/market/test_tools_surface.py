"""The opinion every tool's description has to hold up, since it is the only thing a model knows before
calling it, and the ceiling on what that surface costs to publish."""

from __future__ import annotations

import json

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


async def test_the_expected_tools_and_no_others(tool_server) -> None:
    tools = await tool_server.list_tools()
    assert {t.name for t in tools} == EXPECTED_TOOL_NAMES


async def test_time_tools_name_the_timezone(tool_server) -> None:
    by_name = {t.name: t for t in await tool_server.list_tools()}
    for name in TIME_TOOLS:
        description = by_name[name].description or ""
        assert "UTC" in description, f"{name} does not name the timezone"


# Characters of the serialized `list_tools()`, which an MCP client reads before every turn. In characters
# rather than tokens so the test needs no tokenizer; the measured ratio here is 4,2, so this is ~4 700.
SURFACE_CEILING_CHARS = 19700

# Measured 18 844 characters on 19 August 2026, immediately after the tools moved into this module —
# the same surface the separate process published. Written down so headroom reads as headroom.


def _surface(tools) -> str:
    return json.dumps(
        [t.model_dump(exclude_none=True) for t in tools], separators=(",", ":"), ensure_ascii=False
    )


async def test_the_surface_stays_under_its_ceiling(tool_server) -> None:
    measured = len(_surface(await tool_server.list_tools()))
    assert measured <= SURFACE_CEILING_CHARS, (
        f"the tool surface is {measured} characters, above the {SURFACE_CEILING_CHARS} "
        "ceiling. Shorten a description, narrow a reply, or raise the ceiling on purpose."
    )


async def test_the_schema_still_says_what_a_reply_holds(tool_server) -> None:
    """The other half of the ceiling: a surface kept under it by publishing nothing would
    be cheap and useless, so a reply's shape still has to be described."""
    by_name = {t.name: t for t in await tool_server.list_tools()}
    output = by_name["compute_indicators"].outputSchema
    assert output is not None
    assert output["required"]
    assert all("type" in p or "anyOf" in p or "$ref" in p for p in output["properties"].values())


async def test_the_catalogue_still_publishes_a_parameter_default(tool_server) -> None:
    """The catalogue is only "enough to build a request" if the defaults are in it. `default` is a field
    name here and a JSON Schema keyword everywhere else, and the first slimmer took this one out."""
    by_name = {t.name: t for t in await tool_server.list_tools()}
    for tool in ("list_indicators", "describe_indicator"):
        schema = by_name[tool].outputSchema
        assert schema is not None
        parameter = schema["$defs"]["IndicatorParamOut"]["properties"]
        assert set(parameter) == {"name", "type", "default", "min", "max"}, tool
