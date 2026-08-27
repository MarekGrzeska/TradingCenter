"""`summarize_range`, `describe_coverage` and `search_instruments` — one file, because nothing separated
them but a filename: every case goes through `tool_server` and reads a structured reply."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from mcp.server.fastmcp.exceptions import ToolError
from tools_double import candle, coverage_range, tracked

from market_data.errors import GatewayError
from market_data.reads import Series


def _at(minute: int, open_: float, high: float, low: float, close: float):
    base = datetime(2026, 1, 1, tzinfo=UTC)
    return candle(base + timedelta(minutes=minute), open_=open_, high=high, low=low, close=close)


async def test_summary_reports_change_and_biggest_move(tool_server, archive) -> None:
    archive.with_series(
        [
            _at(0, open_=100, high=102, low=99, close=101),
            _at(1, open_=101, high=110, low=100, close=108),  # biggest move: +7
            _at(2, open_=108, high=109, low=105, close=106),
        ]
    )

    _content, structured = await tool_server.call_tool("summarize_range", {"symbol": "US100"})

    assert structured["candle_count"] == 3
    assert structured["open"] == 100
    assert structured["close"] == 106
    assert structured["high"] == 110
    assert structured["low"] == 99
    assert structured["change"] == 6
    assert structured["biggest_move"] == 7
    assert structured["gap_count"] == 0


async def test_summary_counts_gaps(tool_server, archive) -> None:
    gap = (
        datetime(2026, 1, 1, 0, 10, tzinfo=UTC),
        datetime(2026, 1, 1, 0, 20, tzinfo=UTC),
    )
    archive.series = Series(
        candles=[_at(0, 100, 101, 99, 100)], derived=False, uncovered=[gap]
    )

    _content, structured = await tool_server.call_tool("summarize_range", {"symbol": "US100"})

    assert structured["gap_count"] == 1
    assert any("never verified" in note for note in structured["notes"])


async def test_summary_of_empty_series_names_why(tool_server, archive) -> None:
    archive.pairs = []

    _content, structured = await tool_server.call_tool("summarize_range", {"symbol": "US100"})

    assert structured["candle_count"] == 0
    assert structured["change"] is None
    assert any("nobody is collecting it" in note for note in structured["notes"])



def _range(day: int, history_ended: bool = False):
    return coverage_range(
        datetime(2026, 1, day, tzinfo=UTC),
        datetime(2026, 1, day, 23, 59, 59, tzinfo=UTC),
        history_ended=history_ended,
    )


async def test_coverage_reports_ranges_and_boundary(tool_server, archive) -> None:
    archive.with_coverage(
        [_range(1), _range(2)], earliest=datetime(2020, 1, 1, tzinfo=UTC)
    )

    _content, structured = await tool_server.call_tool("describe_coverage", {"symbol": "US100"})

    assert len(structured["ranges"]) == 2
    assert structured["earliest_reachable"].startswith("2020-01-01")
    assert structured["omitted_ranges"] == 0


async def test_coverage_beyond_the_limit_is_truncated_and_named(tool_server, archive) -> None:
    archive.with_coverage([_range(day) for day in range(1, 26)])  # 25 ranges, limit is 20

    _content, structured = await tool_server.call_tool("describe_coverage", {"symbol": "US100"})

    assert len(structured["ranges"]) == 20
    assert structured["omitted_ranges"] == 5
    assert any("omitted" in note for note in structured["notes"])
    # the most recent ranges are the ones kept
    assert structured["ranges"][0]["from"].startswith("2026-01-25")


async def test_no_coverage_for_untracked_pair(tool_server, archive) -> None:
    archive.pairs = []

    _content, structured = await tool_server.call_tool("describe_coverage", {"symbol": "US100"})

    assert structured["ranges"] == []
    assert any("nobody is collecting it" in note for note in structured["notes"])


async def test_no_coverage_for_a_tracked_pair_points_elsewhere(tool_server, archive) -> None:
    archive.pairs = [tracked()]

    _content, structured = await tool_server.call_tool("describe_coverage", {"symbol": "US100"})

    assert not any("nobody is collecting it" in note for note in structured["notes"])



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
    """The one tool whose answer still crosses a network. A failure there must reach the model as a
    refusal naming the gateway, never as an empty result set, which reads as "no such instrument"."""
    tool_server._fake_app.state.instruments.error = GatewayError("the gateway did not answer")

    with pytest.raises(ToolError) as err:
        await tool_server.call_tool("search_instruments", {"query": "nasdaq"})

    assert "catalogue is unreachable" in str(err.value)
