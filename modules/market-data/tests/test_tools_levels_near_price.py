"""One list of everything the catalogue can put on a chart near the current price. Against the real
catalogue, so the survey is the real one: sixteen entries, which is two chunks rather than one."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from mcp.server.fastmcp.exceptions import ToolError
from tools_double import candle, tracked

from market_data.contract import (
    IndicatorLevelOut,
    IndicatorMarkerOut,
    IndicatorResultOut,
    IndicatorsOut,
    IndicatorZoneOut,
    PriceSide,
    Resolution,
)
from market_data.indicators import service

START = datetime(2026, 1, 1, tzinfo=UTC)

# What each of the three shapes answers with when a test wants that entry to say something. Everything
# else answers empty — an empty shape is the only way to say "this indicator found nothing here".
SPOKEN = {
    "htf_levels_day": [IndicatorLevelOut(from_=START, price=103.0, label="PDH")],
    "range_gap": [
        IndicatorZoneOut(from_=START, to=None, top=99.0, bottom=97.0, direction="bullish")
    ],
    "swing_points": [IndicatorMarkerOut(time=START, label="swing high", price=106.0)],
}


def _outputs() -> dict[str, str]:
    return {entry.id: entry.output for entry in service.catalogue().indicators}


def _answering(spoken: dict | None = None):
    """Answer whatever the chunk asked for, in each entry's own output shape."""
    said = SPOKEN if spoken is None else spoken
    outputs = _outputs()

    def compute(_symbol: str, request) -> IndicatorsOut:
        results = []
        for spec in request.specs:
            shape = outputs[spec.id]
            values = said.get(spec.id, [])
            results.append(
                IndicatorResultOut(
                    id=spec.id,
                    params={},
                    settled=True,
                    **{shape: values},
                )
            )
        return IndicatorsOut(
            symbol="US100",
            resolution=Resolution.MINUTE,
            price_side=PriceSide.BID,
            derived=False,
            algorithm_version=1,
            times=[START + timedelta(minutes=i) for i in range(3)],
            warmup_from=None,
            uncovered=[],
            results=results,
        )

    return compute


async def test_merges_levels_zones_and_markers_sorted_by_distance(tool_server, archive) -> None:
    archive.with_series([candle(START, close=100.0)])
    archive.compute_with = _answering()

    _content, structured = await tool_server.call_tool(
        "levels_near_price", {"symbol": "US100"}
    )

    assert structured["reference_price"] == 100.0
    kinds_by_distance = [item["kind"] for item in structured["items"]]
    # range_gap midpoint=98 (distance 2), htf_levels_day=103 (3), swing_points=106 (6)
    assert kinds_by_distance == ["zone", "level", "marker"]


async def test_no_candidates_for_a_group_is_refused(tool_server) -> None:
    """`averages` is all `lines` — nothing in it can sit on a price axis as a level."""
    with pytest.raises(ToolError, match="no levels/zones/markers"):
        await tool_server.call_tool(
            "levels_near_price", {"symbol": "US100", "group": "averages"}
        )


async def test_no_price_to_measure_from_is_refused(tool_server, archive) -> None:
    archive.pairs = []

    with pytest.raises(ToolError, match="nobody is collecting it"):
        await tool_server.call_tool("levels_near_price", {"symbol": "US100"})


async def test_a_tracked_pair_with_an_empty_window_is_refused_differently(
    tool_server, archive
) -> None:
    """The same empty list, the other reason for it — and the two send an operator to
    different places (specs/market-data-answers)."""
    archive.pairs = [tracked()]

    with pytest.raises(ToolError, match="this window has no candle"):
        await tool_server.call_tool("levels_near_price", {"symbol": "US100"})


async def test_more_candidates_than_the_batch_size_are_all_surveyed(
    tool_server, archive
) -> None:
    archive.with_series([candle(START, close=100.0)])
    every_entry = {
        entry.id: (
            [IndicatorMarkerOut(time=START, label=entry.id, price=101.0)]
            if entry.output == "markers"
            else [IndicatorLevelOut(from_=START, price=101.0, label=entry.id)]
            if entry.output == "levels"
            else [IndicatorZoneOut(from_=START, top=102.0, bottom=100.0)]
        )
        for entry in service.catalogue().indicators
        if entry.output in ("levels", "zones", "markers")
    }
    archive.compute_with = _answering(every_entry)

    _content, structured = await tool_server.call_tool("levels_near_price", {"symbol": "US100"})

    # 16 candidates batched into ceil(16/10) = 2 calls, and every one of them surveyed.
    assert len(archive.computations) == 2
    surveyed = {
        spec.id for _symbol, request in archive.computations for spec in request.specs
    }
    assert surveyed == set(every_entry)
    assert structured["omitted"] == len(every_entry) - len(structured["items"])


async def test_a_group_narrows_the_survey(tool_server, archive) -> None:
    archive.with_series([candle(START, close=100.0)])
    archive.compute_with = _answering()

    _content, structured = await tool_server.call_tool(
        "levels_near_price", {"symbol": "US100", "group": "zones"}
    )

    assert structured["group"] == "zones"
    surveyed = {
        spec.id for _symbol, request in archive.computations for spec in request.specs
    }
    assert surveyed == {
        entry.id for entry in service.catalogue().indicators if entry.group == "zones"
    }
