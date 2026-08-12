from __future__ import annotations

import httpx
import pytest
import respx
from mcp.server.fastmcp.exceptions import ToolError

BASE = "http://127.0.0.1:8020"

CATALOGUE = {
    "algorithm_version": 3,
    "indicators": [
        {
            "id": "ema",
            "name": "EMA",
            "aliases": ["exponential_moving_average"],
            "group": "averages",
            "output": "lines",
            "params": [{"name": "period", "type": "int", "default": 20, "min": 2, "max": 500}],
            "lines": [{"key": "ema", "label": "EMA {period}", "style": None}],
            "render": {
                "pane": "price",
                "style": "line",
                "scale": "price",
                "autoscale": True,
                "range": None,
                "levels": [],
            },
            "warmup_kind": "decay",
        },
        {
            "id": "macd",
            "name": "MACD",
            "aliases": ["macd_hist"],
            "group": "oscillators",
            "output": "lines",
            "params": [],
            "lines": [],
            "render": {
                "pane": "own",
                "style": "line",
                "scale": "own",
                "autoscale": True,
                "range": None,
                "levels": [],
            },
            "warmup_kind": "decay",
        },
    ],
}


@respx.mock
async def test_list_indicators_reads_the_whole_catalogue(server) -> None:
    mcp, upstream = server
    route = respx.get(f"{BASE}/indicators").mock(return_value=httpx.Response(200, json=CATALOGUE))

    _content, structured = await mcp.call_tool("list_indicators", {})

    assert structured["algorithm_version"] == 3
    assert {i["id"] for i in structured["indicators"]} == {"ema", "macd"}
    assert route.called
    await upstream.aclose()


@respx.mock
async def test_list_indicators_filters_by_group(server) -> None:
    mcp, upstream = server
    respx.get(f"{BASE}/indicators").mock(return_value=httpx.Response(200, json=CATALOGUE))

    _content, structured = await mcp.call_tool("list_indicators", {"group": "averages"})

    assert [i["id"] for i in structured["indicators"]] == ["ema"]
    await upstream.aclose()


@respx.mock
async def test_catalogue_is_fetched_once_across_calls(server) -> None:
    mcp, upstream = server
    route = respx.get(f"{BASE}/indicators").mock(return_value=httpx.Response(200, json=CATALOGUE))

    await mcp.call_tool("list_indicators", {})
    await mcp.call_tool("list_indicators", {})
    await mcp.call_tool("describe_indicator", {"id": "ema"})

    assert route.call_count == 1
    await upstream.aclose()


@respx.mock
async def test_describe_indicator_returns_full_entry(server) -> None:
    mcp, upstream = server
    respx.get(f"{BASE}/indicators").mock(return_value=httpx.Response(200, json=CATALOGUE))

    _content, structured = await mcp.call_tool("describe_indicator", {"id": "ema"})

    assert structured["id"] == "ema"
    assert structured["params"][0]["min"] == 2
    assert structured["render"]["pane"] == "price"
    await upstream.aclose()


@respx.mock
async def test_describe_unknown_indicator_points_at_the_catalogue(server) -> None:
    mcp, upstream = server
    respx.get(f"{BASE}/indicators").mock(return_value=httpx.Response(200, json=CATALOGUE))

    with pytest.raises(ToolError, match="list_indicators"):
        await mcp.call_tool("describe_indicator", {"id": "rsi"})
    await upstream.aclose()


@respx.mock
async def test_describe_by_alias_names_the_canonical_id(server) -> None:
    mcp, upstream = server
    respx.get(f"{BASE}/indicators").mock(return_value=httpx.Response(200, json=CATALOGUE))

    with pytest.raises(ToolError, match="'macd'"):
        await mcp.call_tool("describe_indicator", {"id": "macd_hist"})
    await upstream.aclose()
