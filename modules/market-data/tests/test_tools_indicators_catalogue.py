"""The two catalogue tools, against the catalogue this module publishes itself. What the module's
catalogue *contains* is tested next door; this is about what the tools do with it."""

from __future__ import annotations

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from market_data.indicators import service


async def test_list_indicators_reads_the_whole_catalogue(tool_server) -> None:
    published = service.catalogue()

    _content, structured = await tool_server.call_tool("list_indicators", {})

    assert structured["algorithm_version"] == published.algorithm_version
    assert {i["id"] for i in structured["indicators"]} == {e.id for e in published.indicators}


async def test_list_indicators_filters_by_group(tool_server) -> None:
    _content, structured = await tool_server.call_tool("list_indicators", {"group": "averages"})

    assert {i["id"] for i in structured["indicators"]} == {
        e.id for e in service.catalogue().indicators if e.group == "averages"
    }
    assert structured["group"] == "averages"


async def test_the_catalogue_is_read_once_across_calls(tool_server, monkeypatch) -> None:
    """It was cached because a fetch cost a request. There is no request now, and the cache is down to
    the two lookups `_Catalogue` builds — still worth building once."""
    reads = {"n": 0}
    original = service.catalogue

    def counted():
        reads["n"] += 1
        return original()

    monkeypatch.setattr(service, "catalogue", counted)

    await tool_server.call_tool("list_indicators", {})
    await tool_server.call_tool("list_indicators", {})
    await tool_server.call_tool("describe_indicator", {"id": "ema"})

    assert reads["n"] == 1


async def test_describe_indicator_returns_full_entry(tool_server) -> None:
    _content, structured = await tool_server.call_tool("describe_indicator", {"id": "ema"})

    assert structured["id"] == "ema"
    assert structured["params"][0]["name"] == "period"
    assert structured["params"][0]["min"] == 2
    assert structured["render"]["pane"] == "price"
    assert structured["lines"][0]["label"] == "EMA {period}"


async def test_describe_unknown_indicator_points_at_the_catalogue(tool_server) -> None:
    with pytest.raises(ToolError, match="list_indicators"):
        await tool_server.call_tool("describe_indicator", {"id": "moonphase"})


async def test_describe_by_alias_names_the_canonical_id(tool_server) -> None:
    """`Williams Fractal` is a name the catalogue answers to, and `swing_points` is what
    it is called. Named rather than substituted (specs/market-data-tools)."""
    with pytest.raises(ToolError, match="swing_points"):
        await tool_server.call_tool("describe_indicator", {"id": "Williams Fractal"})
