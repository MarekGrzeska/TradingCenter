from __future__ import annotations

import json

import httpx
import respx

BASE = "http://127.0.0.1:8020"


@respx.mock
async def test_pairs_resource_reads_market_data(server) -> None:
    mcp, upstream = server
    respx.get(f"{BASE}/pairs").mock(return_value=httpx.Response(200, json=[{"symbol": "US100"}]))

    [content] = await mcp.read_resource("market://pairs")

    assert json.loads(content.content) == [{"symbol": "US100"}]
    await upstream.aclose()


@respx.mock
async def test_indicators_catalogue_resource(server) -> None:
    mcp, upstream = server
    respx.get(f"{BASE}/indicators").mock(
        return_value=httpx.Response(200, json={"algorithm_version": 1, "indicators": []})
    )

    [content] = await mcp.read_resource("market://indicators/catalogue")

    assert json.loads(content.content)["algorithm_version"] == 1
    await upstream.aclose()


@respx.mock
async def test_coverage_resource_template_substitutes_symbol_and_resolution(server) -> None:
    mcp, upstream = server
    respx.get(f"{BASE}/coverage/US100").mock(
        return_value=httpx.Response(
            200,
            json={
                "symbol": "US100",
                "resolution": "HOUR",
                "ranges": [],
                "earliest_reachable": None,
            },
        )
    )

    [content] = await mcp.read_resource("market://coverage/US100/HOUR")

    assert json.loads(content.content)["resolution"] == "HOUR"
    await upstream.aclose()


async def test_resources_are_listed(server) -> None:
    mcp, upstream = server

    resources = [str(r.uri) for r in await mcp.list_resources()]
    templates = [t.uriTemplate for t in await mcp.list_resource_templates()]

    assert "market://pairs" in resources
    assert "market://indicators/catalogue" in resources
    assert "market://coverage/{symbol}/{resolution}" in templates
    await upstream.aclose()


async def test_analyze_symbol_prompt_orders_the_steps(server) -> None:
    mcp, upstream = server

    result = await mcp.get_prompt("analyze-symbol", {"symbol": "US100"})

    text = result.messages[0].content.text
    coverage_at = text.index("describe_coverage")
    summary_at = text.index("summarize_range")
    indicators_at = text.index("compute_indicators")
    unknowns_at = text.index("name explicitly what is not known")
    assert coverage_at < summary_at < indicators_at < unknowns_at
    assert "US100" in text
    await upstream.aclose()
