"""One refusal shape for every tool, and the reasons an empty answer can have. A refusal used to arrive
from across the wire as a 422; in-process each one has to be raised where the tool stands."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from mcp.server.fastmcp.exceptions import ToolError
from tools_double import candle, series, tracked

from market_data.models import Resolution

RESOLUTION_TAKING = [
    ("get_candles", {"symbol": "US100", "resolution": "SECOND"}),
    ("get_last_price", {"symbol": "US100", "resolution": "SECOND"}),
    ("summarize_range", {"symbol": "US100", "resolution": "SECOND"}),
    ("describe_coverage", {"symbol": "US100", "resolution": "SECOND"}),
    ("compute_indicators", {"symbol": "US100", "specs": [{"id": "ema"}], "resolution": "SECOND"}),
    ("levels_near_price", {"symbol": "US100", "resolution": "SECOND"}),
]


@pytest.mark.parametrize("tool_name,arguments", RESOLUTION_TAKING)
async def test_an_unknown_resolution_is_refused_by_every_tool_that_takes_one(
    tool_server, archive, tool_name: str, arguments: dict
) -> None:
    """FastAPI used to refuse this before a handler ran, and the tool never saw it. Here the enum is
    reached directly, and without `resolution_of` the tool would raise a bare ValueError."""
    archive.with_series(series(3))
    archive.pairs = [tracked()]

    with pytest.raises(ToolError) as refused:
        await tool_server.call_tool(tool_name, arguments)

    assert "unknown resolution 'SECOND'" in str(refused.value)
    # The refusal says what the archive does know, so the next call can be right.
    assert Resolution.MINUTE.value in str(refused.value)


WINDOW_TAKING = [
    ("get_candles", {"symbol": "US100"}),
    ("summarize_range", {"symbol": "US100"}),
    ("compute_indicators", {"symbol": "US100", "specs": [{"id": "ema"}], "mode": "series"}),
]


@pytest.mark.parametrize("tool_name,arguments", WINDOW_TAKING)
async def test_a_reversed_range_is_refused_by_every_tool_that_takes_one(
    tool_server, tool_name: str, arguments: dict
) -> None:
    """The regression this move could have shipped: over the wire a backwards range was a 422; in-process
    the query matches nothing, so the answer would have been "no candles" dressed as a quiet market."""
    with pytest.raises(ToolError) as refused:
        await tool_server.call_tool(
            tool_name,
            {**arguments, "from_iso": "2026-08-11T10:00:00Z", "to_iso": "2026-08-11T09:00:00Z"},
        )

    assert "is before" in str(refused.value)
    assert "Swap the two bounds" in str(refused.value)


async def test_too_large_a_series_is_refused_with_what_to_do_instead(
    tool_server, archive
) -> None:
    archive.with_series(series(2500))

    with pytest.raises(ToolError) as refused:
        await tool_server.call_tool("get_candles", {"symbol": "US100"})

    assert "coarser resolution" in str(refused.value)



async def test_reason_one_nobody_tracks_the_pair(tool_server, archive) -> None:
    archive.pairs = []

    _content, structured = await tool_server.call_tool("get_candles", {"symbol": "US100"})

    assert any("nobody is collecting it" in note for note in structured["notes"])


async def test_reason_two_the_window_is_unverified(tool_server, archive) -> None:
    gap = (
        datetime(2026, 8, 11, 9, tzinfo=UTC),
        datetime(2026, 8, 11, 9, 30, tzinfo=UTC),
    )
    archive.with_series([candle(datetime(2026, 8, 11, 9, 35, tzinfo=UTC))], uncovered=[gap])

    _content, structured = await tool_server.call_tool("get_candles", {"symbol": "US100"})

    assert any("never verified" in note for note in structured["notes"])
    assert not any("nobody is collecting it" in note for note in structured["notes"])


async def test_reason_three_the_archive_could_not_be_read(tool_server, archive) -> None:
    """The read failing is not an empty window. It used to be a timeout and is a database failure now;
    either way a tool answering "no candles" would report a quiet market it never looked at."""
    archive.series_error = RuntimeError("connection was closed in the middle of a query")

    with pytest.raises(ToolError, match="connection was closed"):
        await tool_server.call_tool("get_candles", {"symbol": "US100"})


async def test_the_three_reasons_read_differently(tool_server, archive) -> None:
    """The point of the rule in one assertion: none of the sentences are interchangeable
    — a caller reading one must not confuse it for another."""
    archive.pairs = []
    _content, untracked = await tool_server.call_tool("get_candles", {"symbol": "US100"})

    archive.pairs = [tracked(candle_count=1)]
    _content, unverified = await tool_server.call_tool("get_candles", {"symbol": "US100"})

    assert untracked["notes"] != unverified["notes"]
