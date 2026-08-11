from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import respx

BASE = "http://127.0.0.1:8020"


def _candle(minute: int, open_: float, high: float, low: float, close: float) -> dict:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    return {
        "time": (base + timedelta(minutes=minute)).isoformat(),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": 1,
    }


def _candles_response(candles: list[dict], uncovered: list[dict] | None = None):
    return httpx.Response(
        200,
        json={
            "symbol": "US100",
            "resolution": "MINUTE",
            "price_side": "BID",
            "derived": False,
            "candles": candles,
            "uncovered": uncovered or [],
        },
    )


@respx.mock
async def test_summary_reports_change_and_biggest_move(server) -> None:
    mcp, upstream = server
    candles = [
        _candle(0, open_=100, high=102, low=99, close=101),
        _candle(1, open_=101, high=110, low=100, close=108),  # biggest move: +7
        _candle(2, open_=108, high=109, low=105, close=106),
    ]
    respx.get(f"{BASE}/candles/US100").mock(return_value=_candles_response(candles))

    _content, structured = await mcp.call_tool("summarize_range", {"symbol": "US100"})

    assert structured["candle_count"] == 3
    assert structured["open"] == 100
    assert structured["close"] == 106
    assert structured["high"] == 110
    assert structured["low"] == 99
    assert structured["change"] == 6
    assert structured["biggest_move"] == 7
    assert structured["gap_count"] == 0
    await upstream.aclose()


@respx.mock
async def test_summary_counts_gaps(server) -> None:
    mcp, upstream = server
    gap = {"from": "2026-01-01T00:10:00Z", "to": "2026-01-01T00:20:00Z"}
    respx.get(f"{BASE}/candles/US100").mock(
        return_value=_candles_response([_candle(0, 100, 101, 99, 100)], uncovered=[gap])
    )

    _content, structured = await mcp.call_tool("summarize_range", {"symbol": "US100"})

    assert structured["gap_count"] == 1
    assert any("never verified" in note for note in structured["notes"])
    await upstream.aclose()


@respx.mock
async def test_summary_of_empty_series_names_why(server) -> None:
    mcp, upstream = server
    respx.get(f"{BASE}/candles/US100").mock(return_value=_candles_response([]))
    respx.get(f"{BASE}/pairs").mock(return_value=httpx.Response(200, json=[]))

    _content, structured = await mcp.call_tool("summarize_range", {"symbol": "US100"})

    assert structured["candle_count"] == 0
    assert structured["change"] is None
    assert any("nobody is collecting it" in note for note in structured["notes"])
    await upstream.aclose()
