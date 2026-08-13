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


def _pairs_response(latest_candle: str | None):
    return httpx.Response(
        200,
        json=[
            {
                "symbol": "US100",
                "resolution": "DAY",
                "collection": "collecting",
                "candle_count": 191,
                "latest_candle": latest_candle,
            }
        ],
    )


@respx.mock
async def test_daily_price_older_than_the_default_window_is_still_answered(server) -> None:
    """A DAY candle is always older than the one-day default window, and a Monday's
    newest MINUTE candle is from Friday. The archive holds the price in both cases."""
    mcp, upstream = server
    moment = datetime.now(UTC) - timedelta(days=3)
    route = respx.get(f"{BASE}/candles/US100").mock(
        side_effect=[
            _candles_response([]),
            _candles_response(
                [
                    {
                        "time": moment.isoformat(),
                        "open": 100,
                        "high": 101,
                        "low": 99,
                        "close": 29523.2,
                        "volume": 1,
                    }
                ]
            ),
        ]
    )
    respx.get(f"{BASE}/pairs").mock(return_value=_pairs_response(moment.isoformat()))

    _content, structured = await mcp.call_tool(
        "get_last_price", {"symbol": "US100", "resolution": "DAY"}
    )

    assert structured["close"] == 29523.2
    assert structured["age_seconds"] > timedelta(days=2).total_seconds()
    assert not structured["notes"]
    # The second read is the archive's own instant, not a widened guess.
    assert route.calls[1].request.url.params["from"] == moment.isoformat()
    await upstream.aclose()


@respx.mock
async def test_tracked_pair_with_no_candle_at_all_says_so(server) -> None:
    mcp, upstream = server
    respx.get(f"{BASE}/candles/US100").mock(return_value=_candles_response([]))
    respx.get(f"{BASE}/pairs").mock(return_value=_pairs_response(None))

    _content, structured = await mcp.call_tool(
        "get_last_price", {"symbol": "US100", "resolution": "DAY"}
    )

    assert structured["time"] is None
    assert any("is tracked, but this window has no candle" in note for note in structured["notes"])
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
