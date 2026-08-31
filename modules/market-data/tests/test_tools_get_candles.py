from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from mcp.server.fastmcp.exceptions import ToolError
from tools_double import series, tracked

from market_data.models import Resolution
from market_data.reads import Series


async def test_small_series_is_returned_unaggregated(tool_server, archive) -> None:
    archive.with_series(series(5))

    _content, structured = await tool_server.call_tool("get_candles", {"symbol": "US100"})

    assert structured["aggregated"] is False
    assert structured["original_candle_count"] is None
    assert len(structured["candles"]) == 5


async def test_series_above_ceiling_is_aggregated_and_named(tool_server, archive) -> None:
    archive.with_series(series(450))

    _content, structured = await tool_server.call_tool("get_candles", {"symbol": "US100"})

    assert structured["aggregated"] is True
    assert structured["original_candle_count"] == 450
    assert len(structured["candles"]) <= 200
    assert any("Aggregated 450" in note for note in structured["notes"])


async def test_series_far_above_ceiling_is_refused_with_guidance(tool_server, archive) -> None:
    archive.with_series(series(2500))

    with pytest.raises(ToolError, match="coarser resolution"):
        await tool_server.call_tool("get_candles", {"symbol": "US100"})


async def test_a_years_daily_window_stays_within_a_character_budget(
    tool_server, archive
) -> None:
    """DAY candles over roughly a year — aggregation must keep the reply well under a budget small
    enough that a model reading it is reading a summary, not a re-serialized archive."""
    archive.with_series(series(365, start=datetime(2025, 1, 1, tzinfo=UTC)))

    _content, structured = await tool_server.call_tool(
        "get_candles",
        {
            "symbol": "US100",
            "resolution": "DAY",
            "from_iso": "2025-01-01T00:00:00Z",
            "to_iso": "2026-01-01T00:00:00Z",
        },
    )

    assert structured["aggregated"] is True
    assert len(structured["candles"]) <= 200
    assert len(json.dumps(structured)) < 30_000


async def test_empty_series_for_untracked_pair_names_it_not_quiet(tool_server, archive) -> None:
    archive.pairs = []

    _content, structured = await tool_server.call_tool("get_candles", {"symbol": "US100"})

    assert structured["candles"] == []
    assert any("nobody is collecting it" in note for note in structured["notes"])


async def test_empty_series_for_tracked_pair_points_at_coverage(tool_server, archive) -> None:
    archive.pairs = [tracked(candle_count=10)]

    _content, structured = await tool_server.call_tool("get_candles", {"symbol": "US100"})

    assert any("describe_coverage" in note for note in structured["notes"])


async def test_uncovered_range_is_named_in_the_reply(tool_server, archive) -> None:
    gap = (
        datetime(2026, 8, 11, 9, 0, tzinfo=UTC),
        datetime(2026, 8, 11, 9, 30, tzinfo=UTC),
    )
    archive.series = Series(candles=series(3), derived=False, uncovered=[gap])

    _content, structured = await tool_server.call_tool("get_candles", {"symbol": "US100"})

    assert any("never verified" in note for note in structured["notes"])


async def test_derived_series_is_named_in_the_reply(tool_server, archive) -> None:
    archive.series = Series(candles=series(3), derived=True, uncovered=[])

    _content, structured = await tool_server.call_tool(
        "get_candles", {"symbol": "US100", "resolution": "HOUR"}
    )

    assert any("computed from a finer series" in note for note in structured["notes"])


async def test_a_backwards_window_is_refused_rather_than_answered_empty(
    tool_server, archive
) -> None:
    """The refusal that used to arrive as the archive's own 422. Reading in-process nothing refuses it —
    the query matches nothing — so a backwards range would come back as "no candles"."""
    archive.with_series([])

    with pytest.raises(ToolError, match="is before"):
        await tool_server.call_tool(
            "get_candles",
            {
                "symbol": "US100",
                "from_iso": "2026-08-11T10:00:00Z",
                "to_iso": "2026-08-11T09:00:00Z",
            },
        )


async def test_an_unknown_resolution_is_refused_naming_the_known_ones(
    tool_server, archive
) -> None:
    """The other refusal that used to be the archive's: FastAPI rejected a resolution outside the enum
    before the handler ran. In-process the string reaches the tool, so the tool names the ones that exist."""
    with pytest.raises(ToolError) as err:
        await tool_server.call_tool("get_candles", {"symbol": "US100", "resolution": "FORTNIGHT"})

    assert "FORTNIGHT" in str(err.value)
    assert Resolution.MINUTE.value in str(err.value)
