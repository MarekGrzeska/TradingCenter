from __future__ import annotations

import httpx
import respx

from market_mcp.tools.pairs import _worst_collection

BASE = "http://127.0.0.1:8020"


def _row(symbol: str, resolution: str, collection: str = "collecting") -> dict:
    return {
        "symbol": symbol,
        "resolution": resolution,
        "collection": collection,
        "candle_count": 42,
        "latest_candle": "2020-01-01T00:00:00Z",
    }


def test_all_collecting_summarises_as_collecting() -> None:
    assert _worst_collection(["collecting", "collecting", "collecting"]) == "collecting"


def test_one_stalled_resolution_decides_the_symbol() -> None:
    """The whole reason this summary takes the worst rather than the commonest: six
    healthy timeframes must not hide the seventh that stopped."""
    assert _worst_collection(["collecting"] * 6 + ["stalled"]) == "stalled"


def test_market_closed_loses_to_never_collected() -> None:
    assert _worst_collection(["market_closed", "never_collected"]) == "never_collected"


def test_a_state_this_module_has_never_heard_of_ranks_worst() -> None:
    """market-data naming a new state is not a reason to report the symbol as healthy on
    its behalf — the summary would then be silently wrong in the one direction that
    matters."""
    assert _worst_collection(["collecting", "paused_by_operator"]) == "paused_by_operator"


@respx.mock
async def test_one_row_per_symbol_sorted_and_without_resolutions(server) -> None:
    mcp, upstream = server
    respx.get(f"{BASE}/pairs").mock(
        return_value=httpx.Response(
            200,
            json=[
                _row("US100", "MINUTE_5"),
                _row("US100", "HOUR"),
                _row("GOLD", "MINUTE_5"),
                _row("GOLD", "WEEK"),
                # Out of order on purpose: market-data appends a resolution added later,
                # and the fold must not depend on rows of one symbol being adjacent.
                _row("US100", "MINUTE"),
            ],
        )
    )

    _content, structured = await mcp.call_tool("list_tracked_symbols", {})

    assert structured["result"] == [
        {"symbol": "GOLD", "collection": "collecting"},
        {"symbol": "US100", "collection": "collecting"},
    ]
    await upstream.aclose()


@respx.mock
async def test_the_symbol_carries_its_least_healthy_resolution(server) -> None:
    mcp, upstream = server
    respx.get(f"{BASE}/pairs").mock(
        return_value=httpx.Response(
            200,
            json=[
                _row("US100", "MINUTE_5", "collecting"),
                _row("US100", "HOUR", "stalled"),
                _row("GOLD", "MINUTE_5", "market_closed"),
            ],
        )
    )

    _content, structured = await mcp.call_tool("list_tracked_symbols", {})

    assert structured["result"] == [
        {"symbol": "GOLD", "collection": "market_closed"},
        {"symbol": "US100", "collection": "stalled"},
    ]
    await upstream.aclose()


@respx.mock
async def test_nothing_tracked_is_an_empty_list_not_a_refusal(server) -> None:
    mcp, upstream = server
    respx.get(f"{BASE}/pairs").mock(return_value=httpx.Response(200, json=[]))

    _content, structured = await mcp.call_tool("list_tracked_symbols", {})

    assert structured == {"result": []}
    await upstream.aclose()
