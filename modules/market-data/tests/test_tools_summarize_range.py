from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tools_double import candle

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
