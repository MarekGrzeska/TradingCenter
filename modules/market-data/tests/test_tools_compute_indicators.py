"""What a computed indicator looks like once it has been reduced for a model.

The catalogue is no longer mocked. It used to be fetched over HTTP and every test built a
fake entry to answer that fetch; the tools read the module's own catalogue now, so these
run against the real entries — `ema` really is `lines`, `swing_points` really is `markers`,
and an alias hint really is one of the names the catalogue publishes. What stays doubled is
the computation itself, which needs a database.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from mcp.server.fastmcp.exceptions import ToolError
from tools_double import candle

from market_data.contract import (
    IndicatorMarkerOut,
    IndicatorResultOut,
    IndicatorsOut,
    PriceSide,
    Resolution,
)
from market_data.models import Candle

START = datetime(2026, 1, 1, tzinfo=UTC)


def _times(n: int) -> list[datetime]:
    return [START + timedelta(minutes=i) for i in range(n)]


def _computed(n: int, results: list[IndicatorResultOut], derived: bool = False) -> IndicatorsOut:
    return IndicatorsOut(
        symbol="US100",
        resolution=Resolution.MINUTE,
        price_side=PriceSide.BID,
        derived=derived,
        algorithm_version=1,
        times=_times(n),
        warmup_from=None,
        uncovered=[],
        results=results,
    )


def _candle_at(i: int, close: float) -> Candle:
    """One candle on the same axis the computation answered on — `mode="latest"` measures
    every line's distance against the close standing at its own last time."""
    return candle(
        START + timedelta(minutes=i), open_=close, high=close + 1, low=close - 1, close=close
    )


async def test_latest_mode_reports_value_slope_and_distance(tool_server, archive) -> None:
    ema_values = [100 + i * 0.5 for i in range(20)]  # last=109.5, lookback(idx9)=104.5
    closes = [100 + i * 0.6 for i in range(20)]  # last close=111.4
    archive.computed = _computed(
        20,
        [
            IndicatorResultOut(
                id="ema", params={}, warmup_bars=20, settled=True, lines={"ema": ema_values}
            )
        ],
    )
    archive.with_series([_candle_at(i, close) for i, close in enumerate(closes)])

    _content, structured = await tool_server.call_tool(
        "compute_indicators", {"symbol": "US100", "specs": [{"id": "ema"}]}
    )

    [result] = structured["results"]
    [line] = result["latest"]
    assert line["value"] == pytest.approx(109.5)
    assert line["slope_per_bar"] == pytest.approx(0.5)
    assert line["distance_from_price"] == pytest.approx(1.9)


async def test_series_mode_thins_a_large_series(tool_server, archive) -> None:
    values = [100 + i * 0.1 for i in range(500)]
    archive.computed = _computed(
        500,
        [
            IndicatorResultOut(
                id="ema", params={}, warmup_bars=20, settled=True, lines={"ema": values}
            )
        ],
    )

    _content, structured = await tool_server.call_tool(
        "compute_indicators",
        {
            "symbol": "US100",
            "specs": [{"id": "ema"}],
            "mode": "series",
            "from_iso": "2026-01-01T00:00:00Z",
            "to_iso": "2026-01-01T08:20:00Z",
        },
    )

    [result] = structured["results"]
    assert result["series_thinned"] is True
    assert result["series_original_point_count"] == 500
    assert len(result["series"][0]["values"]) <= 200
    assert len(result["times"]) == len(result["series"][0]["values"])


async def test_markers_are_capped_to_the_freshest_and_named(tool_server, archive) -> None:
    markers = [
        IndicatorMarkerOut(time=START + timedelta(minutes=i), label=f"s{i}", price=100 + i)
        for i in range(30)
    ]
    archive.computed = _computed(
        30,
        [
            IndicatorResultOut(
                id="swing_points", params={}, warmup_bars=0, settled=True, markers=markers
            )
        ],
    )

    _content, structured = await tool_server.call_tool(
        "compute_indicators", {"symbol": "US100", "specs": [{"id": "swing_points"}]}
    )

    [result] = structured["results"]
    assert len(result["markers"]) == 20
    assert result["omitted"] == 10
    assert result["markers"][0]["label"] == "s29"  # newest first


async def test_unsettled_result_carries_its_own_note(tool_server, archive) -> None:
    archive.computed = _computed(
        5,
        [
            IndicatorResultOut(
                id="ema",
                params={},
                warmup_bars=200,
                settled=False,
                lines={"ema": [None, None, None, 101.0, 101.5]},
            )
        ],
    )
    archive.with_series([_candle_at(i, 100.0) for i in range(5)])

    _content, structured = await tool_server.call_tool(
        "compute_indicators", {"symbol": "US100", "specs": [{"id": "ema"}]}
    )

    [result] = structured["results"]
    assert result["settled"] is False
    assert any("200 bars" in note for note in result["notes"])


async def test_error_result_carries_the_archives_own_reason(tool_server, archive) -> None:
    archive.computed = _computed(
        0,
        [
            IndicatorResultOut(
                id="ema",
                params={},
                settled=False,
                error="no MINUTE_5 series collected for 'US100'",
            )
        ],
    )

    _content, structured = await tool_server.call_tool(
        "compute_indicators", {"symbol": "US100", "specs": [{"id": "ema"}]}
    )

    [result] = structured["results"]
    assert result["error"] == "no MINUTE_5 series collected for 'US100'"
    assert result["latest"] is None


async def test_unknown_indicator_is_refused_with_a_hint(tool_server) -> None:
    """"FVG" is a name the catalogue publishes — as an alias of `range_gap`, not as an
    id. Named rather than substituted: a model asking for one indicator and silently
    getting another is worse than being told."""
    with pytest.raises(ToolError, match="range_gap"):
        await tool_server.call_tool(
            "compute_indicators", {"symbol": "US100", "specs": [{"id": "FVG"}]}
        )


async def test_a_name_in_no_entry_is_refused_without_a_hint(tool_server) -> None:
    with pytest.raises(ToolError, match="no indicator named 'moonphase'"):
        await tool_server.call_tool(
            "compute_indicators", {"symbol": "US100", "specs": [{"id": "moonphase"}]}
        )


async def test_too_many_specs_is_refused(tool_server) -> None:
    with pytest.raises(ToolError, match="10-indicator ceiling"):
        await tool_server.call_tool(
            "compute_indicators", {"symbol": "US100", "specs": [{"id": "ema"}] * 11}
        )


async def test_invalid_mode_is_refused(tool_server) -> None:
    with pytest.raises(ToolError, match="mode must be"):
        await tool_server.call_tool(
            "compute_indicators", {"symbol": "US100", "specs": [{"id": "ema"}], "mode": "sideways"}
        )


async def test_an_unknown_resolution_is_refused_here_not_swallowed(tool_server, archive) -> None:
    """The archive's 422 used to refuse this before the request reached a handler. In one
    process there is no request: `Resolution("SECOND")` would raise a ValueError out of the
    read, and the tool would answer with an exception rather than a sentence.
    """
    archive.computed = _computed(0, [])

    with pytest.raises(ToolError, match="unknown resolution 'SECOND'"):
        await tool_server.call_tool(
            "compute_indicators",
            {"symbol": "US100", "specs": [{"id": "ema"}], "resolution": "SECOND"},
        )
