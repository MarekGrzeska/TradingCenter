from __future__ import annotations

import httpx
import respx

BASE = "http://127.0.0.1:8020"


def _instrument(symbol: str) -> dict:
    return {
        "symbol": symbol,
        "name": f"{symbol} instrument",
        "asset_class": "INDEX",
        "tradeable": True,
        "provider": "capital.com",
    }


@respx.mock
async def test_search_returns_matches(server) -> None:
    mcp, upstream = server
    respx.get(f"{BASE}/instruments/search").mock(
        return_value=httpx.Response(200, json=[_instrument("US100")])
    )

    _content, structured = await mcp.call_tool("search_instruments", {"query": "nasdaq"})

    assert structured["results"] == [
        {"symbol": "US100", "name": "US100 instrument", "asset_class": "INDEX", "tradeable": True}
    ]
    assert structured["omitted"] == 0
    await upstream.aclose()


@respx.mock
async def test_search_beyond_the_limit_is_truncated_and_named(server) -> None:
    mcp, upstream = server
    hits = [_instrument(f"SYM{i}") for i in range(15)]
    respx.get(f"{BASE}/instruments/search").mock(return_value=httpx.Response(200, json=hits))

    _content, structured = await mcp.call_tool("search_instruments", {"query": "sym"})

    assert len(structured["results"]) == 10
    assert structured["omitted"] == 5
    await upstream.aclose()


@respx.mock
async def test_search_with_no_matches(server) -> None:
    mcp, upstream = server
    respx.get(f"{BASE}/instruments/search").mock(return_value=httpx.Response(200, json=[]))

    _content, structured = await mcp.call_tool("search_instruments", {"query": "doesnotexist"})

    assert structured["results"] == []
    await upstream.aclose()
