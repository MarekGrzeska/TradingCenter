from __future__ import annotations

import httpx
import respx

from market_mcp.tools.pairs import _pair_out

BASE = "http://127.0.0.1:8020"


def test_pair_out_computes_age_from_latest_candle() -> None:
    row = {
        "symbol": "US100",
        "resolution": "MINUTE",
        "collection": "collecting",
        "candle_count": 42,
        "latest_candle": "2020-01-01T00:00:00Z",
    }
    out = _pair_out(row)
    assert out.symbol == "US100"
    assert out.latest_candle_age_seconds is not None
    assert out.latest_candle_age_seconds > 0


def test_pair_out_with_no_candles_has_no_age() -> None:
    row = {
        "symbol": "US100",
        "resolution": "MINUTE",
        "collection": "never_collected",
        "candle_count": 0,
        "latest_candle": None,
    }
    out = _pair_out(row)
    assert out.latest_candle_age_seconds is None


@respx.mock
async def test_list_tracked_pairs_reads_market_data(server) -> None:
    mcp, upstream = server
    respx.get(f"{BASE}/pairs").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "symbol": "US100",
                    "resolution": "MINUTE",
                    "collection": "collecting",
                    "candle_count": 42,
                    "latest_candle": "2020-01-01T00:00:00Z",
                }
            ],
        )
    )

    _content, structured = await mcp.call_tool("list_tracked_pairs", {})

    [pair] = structured["result"]
    assert pair["symbol"] == "US100"
    assert pair["resolution"] == "MINUTE"
    assert pair["collection"] == "collecting"
    assert pair["candle_count"] == 42
    assert pair["latest_candle_age_seconds"] > 0
    await upstream.aclose()


@respx.mock
async def test_list_tracked_pairs_with_no_pairs(server) -> None:
    mcp, upstream = server
    respx.get(f"{BASE}/pairs").mock(return_value=httpx.Response(200, json=[]))

    _content, structured = await mcp.call_tool("list_tracked_pairs", {})

    assert structured == {"result": []}
    await upstream.aclose()
