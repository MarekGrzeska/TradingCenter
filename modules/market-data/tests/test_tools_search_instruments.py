from __future__ import annotations

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from market_data.errors import GatewayError


def _instrument(symbol: str) -> dict:
    return {
        "symbol": symbol,
        "name": f"{symbol} instrument",
        "asset_class": "INDEX",
        "tradeable": True,
        "provider": "capital.com",
    }


async def test_search_returns_matches(tool_server) -> None:
    tool_server._fake_app.state.instruments.search_results = [_instrument("US100")]

    _content, structured = await tool_server.call_tool("search_instruments", {"query": "nasdaq"})

    assert structured["results"] == [
        {"symbol": "US100", "name": "US100 instrument", "asset_class": "INDEX", "tradeable": True}
    ]
    assert structured["omitted"] == 0


async def test_search_beyond_the_limit_is_truncated_and_named(tool_server) -> None:
    tool_server._fake_app.state.instruments.search_results = [
        _instrument(f"SYM{i}") for i in range(15)
    ]

    _content, structured = await tool_server.call_tool("search_instruments", {"query": "sym"})

    assert len(structured["results"]) == 10
    assert structured["omitted"] == 5


async def test_search_with_no_matches(tool_server) -> None:
    tool_server._fake_app.state.instruments.search_results = []

    _content, structured = await tool_server.call_tool(
        "search_instruments", {"query": "doesnotexist"}
    )

    assert structured["results"] == []


async def test_an_unreachable_catalogue_is_a_refusal_naming_it(tool_server) -> None:
    """The one tool whose answer still crosses a network — the instrument catalogue is
    capital-gateway's, and this archive holds the only key to it. A failure there must
    reach the model as a refusal naming the gateway, never as an empty result set, which
    reads as "no such instrument" (specs/market-data-answers, "Trzy rodzaje «nie wiem»")."""
    tool_server._fake_app.state.instruments.error = GatewayError("the gateway did not answer")

    with pytest.raises(ToolError) as err:
        await tool_server.call_tool("search_instruments", {"query": "nasdaq"})

    assert "catalogue is unreachable" in str(err.value)
