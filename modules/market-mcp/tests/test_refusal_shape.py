"""Task 4.1 (one refusal shape, every tool through the same road) and task 4.2
(three distinct reasons for "I don't know") — checked at the tool boundary, not just
inside `client.py`, since that is what a caller actually sees.
"""

from __future__ import annotations

import httpx
import pytest
import respx
from mcp.server.fastmcp.exceptions import ToolError

BASE = "http://127.0.0.1:8020"


# --- 4.1: every tool's refusal is ToolError, carrying market-data's own detail ---


@respx.mock
@pytest.mark.parametrize(
    "tool_name,arguments,path",
    [
        ("get_candles", {"symbol": "US100"}, f"{BASE}/candles/US100"),
        ("get_last_price", {"symbol": "US100"}, f"{BASE}/candles/US100/forming"),
        ("summarize_range", {"symbol": "US100"}, f"{BASE}/candles/US100"),
        ("describe_coverage", {"symbol": "US100"}, f"{BASE}/coverage/US100"),
        ("search_instruments", {"query": "x"}, f"{BASE}/instruments/search"),
        ("list_tracked_pairs", {}, f"{BASE}/pairs"),
        ("list_indicators", {}, f"{BASE}/indicators"),
    ],
)
async def test_every_tool_refuses_the_same_way(server, tool_name, arguments, path) -> None:
    mcp, upstream = server
    respx.get(path).mock(return_value=httpx.Response(422, json={"detail": "reversed range"}))

    with pytest.raises(ToolError, match="reversed range"):
        await mcp.call_tool(tool_name, arguments)
    await upstream.aclose()


# --- 4.2: three reasons for an empty answer, never collapsed into one ---


def _candles_response(candles: list, uncovered: list | None = None) -> httpx.Response:
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
async def test_reason_one_nobody_tracks_the_pair(server) -> None:
    mcp, upstream = server
    respx.get(f"{BASE}/candles/US100").mock(return_value=_candles_response([]))
    respx.get(f"{BASE}/pairs").mock(return_value=httpx.Response(200, json=[]))

    _content, structured = await mcp.call_tool("get_candles", {"symbol": "US100"})

    assert any("nobody is collecting it" in note for note in structured["notes"])
    await upstream.aclose()


@respx.mock
async def test_reason_two_the_window_is_unverified(server) -> None:
    mcp, upstream = server
    gap = {"from": "2026-08-11T09:00:00Z", "to": "2026-08-11T09:30:00Z"}
    respx.get(f"{BASE}/candles/US100").mock(
        return_value=_candles_response(
            [
                {
                    "time": "2026-08-11T09:35:00Z",
                    "open": 1,
                    "high": 1,
                    "low": 1,
                    "close": 1,
                    "volume": 1,
                }
            ],
            uncovered=[gap],
        )
    )

    _content, structured = await mcp.call_tool("get_candles", {"symbol": "US100"})

    assert any("never verified" in note for note in structured["notes"])
    assert not any("nobody is collecting it" in note for note in structured["notes"])
    await upstream.aclose()


@respx.mock
async def test_reason_three_the_archive_did_not_respond(server) -> None:
    mcp, upstream = server
    respx.get(f"{BASE}/candles/US100").mock(side_effect=httpx.ReadTimeout("timed out"))

    with pytest.raises(ToolError, match="did not respond"):
        await mcp.call_tool("get_candles", {"symbol": "US100"})
    await upstream.aclose()


@respx.mock
async def test_the_three_reasons_read_differently(server) -> None:
    """The point of task 4.2 in one assertion: none of the three sentences are
    interchangeable — a caller reading one must not confuse it for another."""
    mcp, upstream = server

    respx.get(f"{BASE}/candles/US100").mock(return_value=_candles_response([]))
    respx.get(f"{BASE}/pairs").mock(return_value=httpx.Response(200, json=[]))
    _content, untracked = await mcp.call_tool("get_candles", {"symbol": "US100"})

    respx.get(f"{BASE}/pairs").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "symbol": "US100",
                    "resolution": "MINUTE",
                    "collection": "collecting",
                    "candle_count": 1,
                    "latest_candle": None,
                }
            ],
        )
    )
    _content, unverified = await mcp.call_tool("get_candles", {"symbol": "US100"})

    assert untracked["notes"] != unverified["notes"]
    await upstream.aclose()
