"""One tool call asks `/pairs` once.

capital.com counts its 10 requests/second against the account rather than the process,
so a request market-data does not have to serve is budget left for the archive's own
collection. `get_candles` on an untracked pair used to spend three of them on the same
question.
"""

from __future__ import annotations

import httpx
import pytest
import respx
from mcp.server.fastmcp.exceptions import ToolError

from market_mcp import client

BASE = "http://127.0.0.1:8020"

TRACKED = [
    {
        "symbol": "US100",
        "resolution": "MINUTE",
        "collection": "collecting",
        "candle_count": 1,
        "latest_candle": None,
    }
]


def _candles(candles: list) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "symbol": "US100",
            "resolution": "MINUTE",
            "from": "2026-08-18T00:00:00Z",
            "to": "2026-08-18T01:00:00Z",
            "candles": candles,
            "count": len(candles),
            "aggregated": False,
            "original_candle_count": None,
            "uncovered": [],
            "derived": False,
        },
    )


@respx.mock
async def test_one_tool_call_reads_pairs_once(server) -> None:
    """`get_candles` finding nothing asks whether the pair is tracked and at which
    resolutions — two questions, one answer."""
    mcp, upstream = server
    pairs = respx.get(f"{BASE}/pairs").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{BASE}/candles/US100").mock(return_value=_candles([]))

    await mcp.call_tool("get_candles", {"symbol": "US100"})

    assert pairs.call_count == 1
    await upstream.aclose()


@respx.mock
async def test_two_calls_inside_the_window_share_one_answer(server) -> None:
    mcp, upstream = server
    pairs = respx.get(f"{BASE}/pairs").mock(return_value=httpx.Response(200, json=TRACKED))

    await mcp.call_tool("list_tracked_pairs", {})
    await mcp.call_tool("list_tracked_symbols", {})

    assert pairs.call_count == 1
    await upstream.aclose()


@respx.mock
async def test_past_the_window_the_archive_is_asked_again(
    server, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The memo is a duration, not a cache to be invalidated — what is being collected
    changes, and this is how long the module is willing to be behind."""
    mcp, upstream = server
    monkeypatch.setattr(client, "PAIRS_MEMO_SECONDS", 0)
    pairs = respx.get(f"{BASE}/pairs").mock(return_value=httpx.Response(200, json=TRACKED))

    await mcp.call_tool("list_tracked_pairs", {})
    await mcp.call_tool("list_tracked_pairs", {})

    assert pairs.call_count == 2
    await upstream.aclose()


@respx.mock
async def test_a_refusal_is_not_remembered(server) -> None:
    """Remembering one would keep answering with it after market-data came back."""
    mcp, upstream = server
    pairs = respx.get(f"{BASE}/pairs").mock(
        side_effect=[
            httpx.Response(503, json={"detail": "the archive is restarting"}),
            httpx.Response(503, json={"detail": "the archive is restarting"}),
            httpx.Response(200, json=TRACKED),
        ]
    )

    with pytest.raises(ToolError):
        await mcp.call_tool("list_tracked_pairs", {})
    rows = (await mcp.call_tool("list_tracked_pairs", {}))[1]

    # Two for the refusal — this client retries a 5xx once — and one for the answer.
    assert pairs.call_count == 3
    assert rows["result"][0]["symbol"] == "US100"
    await upstream.aclose()
