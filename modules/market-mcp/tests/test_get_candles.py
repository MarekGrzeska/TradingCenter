from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from mcp.server.fastmcp.exceptions import ToolError

BASE = "http://127.0.0.1:8020"


def _series(count: int, start: datetime | None = None) -> list[dict]:
    base = start or datetime(2026, 1, 1, tzinfo=UTC)
    return [
        {
            "time": (base + timedelta(minutes=i)).isoformat(),
            "open": 100 + i,
            "high": 101 + i,
            "low": 99 + i,
            "close": 100 + i,
            "volume": 1,
        }
        for i in range(count)
    ]


def _candles_response(
    candles: list[dict], uncovered: list[dict] | None = None, derived: bool = False
):
    return httpx.Response(
        200,
        json={
            "symbol": "US100",
            "resolution": "MINUTE",
            "price_side": "BID",
            "derived": derived,
            "candles": candles,
            "uncovered": uncovered or [],
        },
    )


@respx.mock
async def test_small_series_is_returned_unaggregated(server) -> None:
    mcp, upstream = server
    respx.get(f"{BASE}/candles/US100").mock(return_value=_candles_response(_series(5)))

    _content, structured = await mcp.call_tool("get_candles", {"symbol": "US100"})

    assert structured["aggregated"] is False
    assert structured["original_candle_count"] is None
    assert len(structured["candles"]) == 5
    await upstream.aclose()


@respx.mock
async def test_series_above_ceiling_is_aggregated_and_named(server) -> None:
    mcp, upstream = server
    respx.get(f"{BASE}/candles/US100").mock(return_value=_candles_response(_series(450)))

    _content, structured = await mcp.call_tool("get_candles", {"symbol": "US100"})

    assert structured["aggregated"] is True
    assert structured["original_candle_count"] == 450
    assert len(structured["candles"]) <= 200
    assert any("Aggregated 450" in note for note in structured["notes"])
    await upstream.aclose()


@respx.mock
async def test_series_far_above_ceiling_is_refused_with_guidance(server) -> None:
    mcp, upstream = server
    respx.get(f"{BASE}/candles/US100").mock(return_value=_candles_response(_series(2500)))

    with pytest.raises(ToolError, match="coarser resolution"):
        await mcp.call_tool("get_candles", {"symbol": "US100"})
    await upstream.aclose()


@respx.mock
async def test_a_years_daily_window_stays_within_a_character_budget(server) -> None:
    """DAY candles over roughly a year (~365 raw, above the 200 target but nowhere
    near the refusal ceiling) — aggregation must keep the reply well under a budget
    small enough that a model reading it is reading a summary, not a re-serialized
    archive (specs/market-mcp-answers, "nic nie znika po cichu" without the answer
    itself defeating the ceiling that names it)."""
    mcp, upstream = server
    respx.get(f"{BASE}/candles/US100").mock(
        return_value=_candles_response(_series(365, start=datetime(2025, 1, 1, tzinfo=UTC)))
    )

    _content, structured = await mcp.call_tool(
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
    await upstream.aclose()


@respx.mock
async def test_empty_series_for_untracked_pair_names_it_not_quiet(server) -> None:
    mcp, upstream = server
    respx.get(f"{BASE}/candles/US100").mock(return_value=_candles_response([]))
    respx.get(f"{BASE}/pairs").mock(return_value=httpx.Response(200, json=[]))

    _content, structured = await mcp.call_tool("get_candles", {"symbol": "US100"})

    assert structured["candles"] == []
    assert any("nobody is collecting it" in note for note in structured["notes"])
    await upstream.aclose()


@respx.mock
async def test_empty_series_for_tracked_pair_points_at_coverage(server) -> None:
    mcp, upstream = server
    respx.get(f"{BASE}/candles/US100").mock(return_value=_candles_response([]))
    respx.get(f"{BASE}/pairs").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "symbol": "US100",
                    "resolution": "MINUTE",
                    "collection": "collecting",
                    "candle_count": 10,
                    "latest_candle": None,
                }
            ],
        )
    )

    _content, structured = await mcp.call_tool("get_candles", {"symbol": "US100"})

    assert any("describe_coverage" in note for note in structured["notes"])
    await upstream.aclose()


@respx.mock
async def test_uncovered_range_is_named_in_the_reply(server) -> None:
    mcp, upstream = server
    gap = {"from": "2026-08-11T09:00:00Z", "to": "2026-08-11T09:30:00Z"}
    respx.get(f"{BASE}/candles/US100").mock(
        return_value=_candles_response(_series(3), uncovered=[gap])
    )

    _content, structured = await mcp.call_tool("get_candles", {"symbol": "US100"})

    assert any("never verified" in note for note in structured["notes"])
    await upstream.aclose()


@respx.mock
async def test_derived_series_is_named_in_the_reply(server) -> None:
    mcp, upstream = server
    respx.get(f"{BASE}/candles/US100").mock(
        return_value=_candles_response(_series(3), derived=True)
    )

    _content, structured = await mcp.call_tool(
        "get_candles", {"symbol": "US100", "resolution": "HOUR"}
    )

    assert any("computed from a finer series" in note for note in structured["notes"])
    await upstream.aclose()


@respx.mock
async def test_archive_refusal_detail_reaches_the_caller(server) -> None:
    mcp, upstream = server
    respx.get(f"{BASE}/candles/US100").mock(
        return_value=httpx.Response(422, json={"detail": "`to` is before `from`"})
    )

    with pytest.raises(ToolError, match="is before"):
        await mcp.call_tool("get_candles", {"symbol": "US100"})
    await upstream.aclose()


@respx.mock
async def test_a_validation_list_is_flattened_rather_than_dropped(server) -> None:
    """FastAPI's *other* refusal shape, and the one this module handed over raw until
    18 August 2026: the repr of a list of dicts, `url` to pydantic's error docs and all.

    A refusal here MUST say what to change (specs/market-mcp-answers), so the field's own
    name travels with the message — `msg` alone is "Field required", which names nothing.
    """
    mcp, upstream = server
    respx.get(f"{BASE}/candles/US100").mock(
        return_value=httpx.Response(
            422,
            json={
                "detail": [
                    {
                        "type": "missing",
                        "loc": ["query", "resolution"],
                        "msg": "Field required",
                        "url": "https://errors.pydantic.dev/2.11/v/missing",
                    }
                ]
            },
        )
    )

    with pytest.raises(ToolError) as err:
        await mcp.call_tool("get_candles", {"symbol": "US100"})

    assert "resolution: Field required" in str(err.value)
    assert "pydantic.dev" not in str(err.value), "the repr of the list must not travel"
    await upstream.aclose()


@respx.mock
async def test_a_json_body_that_is_not_an_object_is_still_a_refusal(server) -> None:
    """`.get()` on a JSON list raised `AttributeError`, which the `except ValueError`
    around it never caught — so a refusal shaped like this reached the turn as a crash
    rather than as an answer."""
    mcp, upstream = server
    respx.get(f"{BASE}/candles/US100").mock(return_value=httpx.Response(500, json=["boom"]))

    with pytest.raises(ToolError) as err:
        await mcp.call_tool("get_candles", {"symbol": "US100"})

    assert "AttributeError" not in str(err.value)
    await upstream.aclose()
