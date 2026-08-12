from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from mcp.server.fastmcp.exceptions import ToolError

BASE = "http://127.0.0.1:8020"
START = datetime(2026, 1, 1, tzinfo=UTC)


def _times(n: int) -> list[str]:
    return [(START + timedelta(minutes=i)).isoformat() for i in range(n)]


def _catalogue(*entries: dict) -> dict:
    return {"algorithm_version": 1, "indicators": list(entries)}


def _lines_entry(entry_id: str, group: str = "averages") -> dict:
    return {
        "id": entry_id,
        "name": entry_id.upper(),
        "aliases": [],
        "group": group,
        "output": "lines",
        "params": [],
        "lines": [{"key": entry_id, "label": entry_id.upper(), "style": None}],
        "render": {
            "pane": "price",
            "style": "line",
            "scale": "price",
            "autoscale": True,
            "range": None,
            "levels": [],
        },
        "warmup_kind": "decay",
    }


def _markers_entry(entry_id: str, group: str = "structure") -> dict:
    return {
        "id": entry_id,
        "name": entry_id,
        "aliases": [],
        "group": group,
        "output": "markers",
        "params": [],
        "lines": [],
        "render": {
            "pane": "price",
            "style": "dots",
            "scale": "price",
            "autoscale": True,
            "range": None,
            "levels": [],
        },
        "warmup_kind": "fixed",
    }


def _candles_response(closes: list[float]) -> httpx.Response:
    candles = [
        {
            "time": (START + timedelta(minutes=i)).isoformat(),
            "open": c,
            "high": c + 1,
            "low": c - 1,
            "close": c,
            "volume": 1,
        }
        for i, c in enumerate(closes)
    ]
    return httpx.Response(
        200,
        json={
            "symbol": "US100",
            "resolution": "MINUTE",
            "price_side": "BID",
            "derived": False,
            "candles": candles,
            "uncovered": [],
        },
    )


def _compute_response(
    n: int, results: list[dict], derived: bool = False, uncovered=None
) -> httpx.Response:
    times = _times(n)
    return httpx.Response(
        200,
        json={
            "symbol": "US100",
            "resolution": "MINUTE",
            "price_side": "BID",
            "derived": derived,
            "algorithm_version": 1,
            "times": times,
            "warmup_from": times[0] if times else None,
            "uncovered": uncovered or [],
            "results": results,
        },
    )


@respx.mock
async def test_latest_mode_reports_value_slope_and_distance(server) -> None:
    mcp, upstream = server
    respx.get(f"{BASE}/indicators").mock(
        return_value=httpx.Response(200, json=_catalogue(_lines_entry("ema")))
    )
    ema_values = [100 + i * 0.5 for i in range(20)]  # last=109.5, lookback(idx9)=104.5
    closes = [100 + i * 0.6 for i in range(20)]  # last close=111.4
    respx.post(f"{BASE}/indicators/US100").mock(
        return_value=_compute_response(
            20,
            [
                {
                    "id": "ema",
                    "params": {},
                    "warmup_bars": 20,
                    "settled": True,
                    "lines": {"ema": ema_values},
                }
            ],
        )
    )
    respx.get(f"{BASE}/candles/US100").mock(return_value=_candles_response(closes))

    _content, structured = await mcp.call_tool(
        "compute_indicators", {"symbol": "US100", "specs": [{"id": "ema"}]}
    )

    [result] = structured["results"]
    [line] = result["latest"]
    assert line["value"] == pytest.approx(109.5)
    assert line["slope_per_bar"] == pytest.approx(0.5)
    assert line["distance_from_price"] == pytest.approx(1.9)
    await upstream.aclose()


@respx.mock
async def test_series_mode_thins_a_large_series(server) -> None:
    mcp, upstream = server
    respx.get(f"{BASE}/indicators").mock(
        return_value=httpx.Response(200, json=_catalogue(_lines_entry("ema")))
    )
    values = [100 + i * 0.1 for i in range(500)]
    respx.post(f"{BASE}/indicators/US100").mock(
        return_value=_compute_response(
            500,
            [
                {
                    "id": "ema",
                    "params": {},
                    "warmup_bars": 20,
                    "settled": True,
                    "lines": {"ema": values},
                }
            ],
        )
    )

    _content, structured = await mcp.call_tool(
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
    await upstream.aclose()


@respx.mock
async def test_markers_are_capped_to_the_freshest_and_named(server) -> None:
    mcp, upstream = server
    respx.get(f"{BASE}/indicators").mock(
        return_value=httpx.Response(200, json=_catalogue(_markers_entry("swing_points")))
    )
    markers = [
        {"time": (START + timedelta(minutes=i)).isoformat(), "label": f"s{i}", "price": 100 + i}
        for i in range(30)
    ]
    respx.post(f"{BASE}/indicators/US100").mock(
        return_value=_compute_response(
            30,
            [
                {
                    "id": "swing_points",
                    "params": {},
                    "warmup_bars": 0,
                    "settled": True,
                    "markers": markers,
                }
            ],
        )
    )

    _content, structured = await mcp.call_tool(
        "compute_indicators", {"symbol": "US100", "specs": [{"id": "swing_points"}]}
    )

    [result] = structured["results"]
    assert len(result["markers"]) == 20
    assert result["omitted"] == 10
    assert result["markers"][0]["label"] == "s29"  # newest first
    await upstream.aclose()


@respx.mock
async def test_unsettled_result_carries_its_own_note(server) -> None:
    mcp, upstream = server
    respx.get(f"{BASE}/indicators").mock(
        return_value=httpx.Response(200, json=_catalogue(_lines_entry("ema")))
    )
    respx.post(f"{BASE}/indicators/US100").mock(
        return_value=_compute_response(
            5,
            [
                {
                    "id": "ema",
                    "params": {},
                    "warmup_bars": 200,
                    "settled": False,
                    "lines": {"ema": [None, None, None, 101.0, 101.5]},
                }
            ],
        )
    )
    respx.get(f"{BASE}/candles/US100").mock(return_value=_candles_response([100] * 5))

    _content, structured = await mcp.call_tool(
        "compute_indicators", {"symbol": "US100", "specs": [{"id": "ema"}]}
    )

    [result] = structured["results"]
    assert result["settled"] is False
    assert any("200 bars" in note for note in result["notes"])
    await upstream.aclose()


@respx.mock
async def test_error_result_carries_the_archives_own_reason(server) -> None:
    mcp, upstream = server
    respx.get(f"{BASE}/indicators").mock(
        return_value=httpx.Response(200, json=_catalogue(_lines_entry("ema")))
    )
    respx.post(f"{BASE}/indicators/US100").mock(
        return_value=_compute_response(
            0,
            [
                {
                    "id": "ema",
                    "params": {},
                    "settled": False,
                    "error": "no MINUTE_5 series collected for 'US100'",
                }
            ],
        )
    )

    _content, structured = await mcp.call_tool(
        "compute_indicators", {"symbol": "US100", "specs": [{"id": "ema"}]}
    )

    [result] = structured["results"]
    assert result["error"] == "no MINUTE_5 series collected for 'US100'"
    assert result["latest"] is None
    await upstream.aclose()


@respx.mock
async def test_unknown_indicator_is_refused_with_a_hint(server) -> None:
    mcp, upstream = server
    entry = _lines_entry("macd")
    entry["aliases"] = ["macd_hist"]
    respx.get(f"{BASE}/indicators").mock(return_value=httpx.Response(200, json=_catalogue(entry)))

    with pytest.raises(ToolError, match="'macd'"):
        await mcp.call_tool(
            "compute_indicators", {"symbol": "US100", "specs": [{"id": "macd_hist"}]}
        )
    await upstream.aclose()


@respx.mock
async def test_too_many_specs_is_refused(server) -> None:
    mcp, upstream = server
    respx.get(f"{BASE}/indicators").mock(
        return_value=httpx.Response(200, json=_catalogue(_lines_entry("ema")))
    )

    with pytest.raises(ToolError, match="10-indicator ceiling"):
        await mcp.call_tool(
            "compute_indicators", {"symbol": "US100", "specs": [{"id": "ema"}] * 11}
        )
    await upstream.aclose()


@respx.mock
async def test_invalid_mode_is_refused(server) -> None:
    mcp, upstream = server
    respx.get(f"{BASE}/indicators").mock(
        return_value=httpx.Response(200, json=_catalogue(_lines_entry("ema")))
    )

    with pytest.raises(ToolError, match="mode must be"):
        await mcp.call_tool(
            "compute_indicators", {"symbol": "US100", "specs": [{"id": "ema"}], "mode": "sideways"}
        )
    await upstream.aclose()
