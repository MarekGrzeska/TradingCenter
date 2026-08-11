from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from mcp.server.fastmcp.exceptions import ToolError

BASE = "http://127.0.0.1:8020"
START = datetime(2026, 1, 1, tzinfo=UTC)


def _catalogue(*entries: dict) -> dict:
    return {"algorithm_version": 1, "indicators": list(entries)}


def _entry(entry_id: str, output: str, group: str = "structure") -> dict:
    return {
        "id": entry_id,
        "name": entry_id,
        "aliases": [],
        "group": group,
        "output": output,
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


def _compute_response(results: list[dict]) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "symbol": "US100",
            "resolution": "MINUTE",
            "price_side": "BID",
            "derived": False,
            "algorithm_version": 1,
            "times": [(START + timedelta(minutes=i)).isoformat() for i in range(3)],
            "warmup_from": None,
            "uncovered": [],
            "results": results,
        },
    )


@respx.mock
async def test_merges_levels_zones_and_markers_sorted_by_distance(server) -> None:
    mcp, upstream = server
    respx.get(f"{BASE}/indicators").mock(
        return_value=httpx.Response(
            200,
            json=_catalogue(
                _entry("prev_day", "levels"),
                _entry("order_blocks", "zones"),
                _entry("swings", "markers"),
            ),
        )
    )
    respx.get(f"{BASE}/candles/US100").mock(return_value=_candles_response([100.0]))
    respx.post(f"{BASE}/indicators/US100").mock(
        return_value=_compute_response(
            [
                {
                    "id": "prev_day",
                    "params": {},
                    "settled": True,
                    "levels": [{"from": START.isoformat(), "price": 103.0, "label": "PDH"}],
                },
                {
                    "id": "order_blocks",
                    "params": {},
                    "settled": True,
                    "zones": [
                        {
                            "from": START.isoformat(),
                            "to": None,
                            "top": 99.0,
                            "bottom": 97.0,
                            "direction": "bullish",
                        }
                    ],
                },
                {
                    "id": "swings",
                    "params": {},
                    "settled": True,
                    "markers": [{"time": START.isoformat(), "label": "swing high", "price": 106.0}],
                },
            ]
        )
    )

    _content, structured = await mcp.call_tool(
        "levels_near_price", {"symbol": "US100", "group": "structure"}
    )

    assert structured["reference_price"] == 100.0
    kinds_by_distance = [item["kind"] for item in structured["items"]]
    # order_blocks midpoint=98 (distance 2), prev_day=103 (distance 3), swings=106 (distance 6)
    assert kinds_by_distance == ["zone", "level", "marker"]
    await upstream.aclose()


@respx.mock
async def test_no_candidates_for_a_group_is_refused(server) -> None:
    mcp, upstream = server
    respx.get(f"{BASE}/indicators").mock(
        return_value=httpx.Response(200, json=_catalogue(_entry("ema", "lines", group="averages")))
    )

    with pytest.raises(ToolError, match="no levels/zones/markers"):
        await mcp.call_tool("levels_near_price", {"symbol": "US100", "group": "structure"})
    await upstream.aclose()


@respx.mock
async def test_no_price_to_measure_from_is_refused(server) -> None:
    mcp, upstream = server
    respx.get(f"{BASE}/indicators").mock(
        return_value=httpx.Response(200, json=_catalogue(_entry("swings", "markers")))
    )
    respx.get(f"{BASE}/candles/US100").mock(
        return_value=httpx.Response(
            200,
            json={
                "symbol": "US100",
                "resolution": "MINUTE",
                "price_side": "BID",
                "derived": False,
                "candles": [],
                "uncovered": [],
            },
        )
    )
    respx.get(f"{BASE}/pairs").mock(return_value=httpx.Response(200, json=[]))

    with pytest.raises(ToolError, match="nobody is collecting it"):
        await mcp.call_tool("levels_near_price", {"symbol": "US100"})
    await upstream.aclose()


@respx.mock
async def test_more_candidates_than_the_batch_size_are_all_surveyed(server) -> None:
    mcp, upstream = server
    entries = [_entry(f"marker_{i}", "markers") for i in range(12)]  # > INDICATOR_HARD_LIMIT
    respx.get(f"{BASE}/indicators").mock(
        return_value=httpx.Response(200, json=_catalogue(*entries))
    )
    respx.get(f"{BASE}/candles/US100").mock(return_value=_candles_response([100.0]))

    call_count = {"n": 0}

    def _respond(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        body = request.content
        import json

        specs = json.loads(body)["specs"]
        results = [
            {
                "id": s["id"],
                "params": {},
                "settled": True,
                "markers": [{"time": START.isoformat(), "label": s["id"], "price": 101.0}],
            }
            for s in specs
        ]
        return _compute_response(results)

    respx.post(f"{BASE}/indicators/US100").mock(side_effect=_respond)

    _content, structured = await mcp.call_tool("levels_near_price", {"symbol": "US100"})

    assert call_count["n"] == 2  # 12 candidates batched into ceil(12/10) = 2 calls
    assert len(structured["items"]) == 12
    await upstream.aclose()
