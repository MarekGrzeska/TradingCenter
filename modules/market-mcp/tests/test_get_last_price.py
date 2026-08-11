from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import respx

BASE = "http://127.0.0.1:8020"


def _candles_response(candles: list[dict], derived: bool = False):
    return httpx.Response(
        200,
        json={
            "symbol": "US100",
            "resolution": "MINUTE",
            "price_side": "BID",
            "derived": derived,
            "candles": candles,
            "uncovered": [],
        },
    )


@respx.mock
async def test_last_price_carries_its_age(server) -> None:
    mcp, upstream = server
    moment = datetime.now(UTC) - timedelta(minutes=5)
    respx.get(f"{BASE}/candles/US100").mock(
        return_value=_candles_response(
            [
                {
                    "time": moment.isoformat(),
                    "open": 100,
                    "high": 101,
                    "low": 99,
                    "close": 100.5,
                    "volume": 1,
                }
            ]
        )
    )

    _content, structured = await mcp.call_tool("get_last_price", {"symbol": "US100"})

    assert structured["close"] == 100.5
    assert structured["age_seconds"] > 0
    assert structured["age_seconds"] < 3600
    await upstream.aclose()


@respx.mock
async def test_last_price_takes_the_newest_candle(server) -> None:
    mcp, upstream = server
    now = datetime.now(UTC)
    respx.get(f"{BASE}/candles/US100").mock(
        return_value=_candles_response(
            [
                {
                    "time": (now - timedelta(minutes=2)).isoformat(),
                    "open": 1,
                    "high": 1,
                    "low": 1,
                    "close": 1,
                    "volume": 1,
                },
                {
                    "time": (now - timedelta(minutes=1)).isoformat(),
                    "open": 2,
                    "high": 2,
                    "low": 2,
                    "close": 2,
                    "volume": 1,
                },
            ]
        )
    )

    _content, structured = await mcp.call_tool("get_last_price", {"symbol": "US100"})

    assert structured["close"] == 2
    await upstream.aclose()


@respx.mock
async def test_no_candle_for_untracked_pair(server) -> None:
    mcp, upstream = server
    respx.get(f"{BASE}/candles/US100").mock(return_value=_candles_response([]))
    respx.get(f"{BASE}/pairs").mock(return_value=httpx.Response(200, json=[]))

    _content, structured = await mcp.call_tool("get_last_price", {"symbol": "US100"})

    assert structured["close"] is None
    assert structured["time"] is None
    assert any("nobody is collecting it" in note for note in structured["notes"])
    await upstream.aclose()
