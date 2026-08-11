from __future__ import annotations

import httpx
import respx

BASE = "http://127.0.0.1:8020"


def _range(day: int, history_ended: bool = False) -> dict:
    return {
        "from": f"2026-01-{day:02d}T00:00:00Z",
        "to": f"2026-01-{day:02d}T23:59:59Z",
        "history_ended": history_ended,
    }


@respx.mock
async def test_coverage_reports_ranges_and_boundary(server) -> None:
    mcp, upstream = server
    respx.get(f"{BASE}/coverage/US100").mock(
        return_value=httpx.Response(
            200,
            json={
                "symbol": "US100",
                "resolution": "MINUTE",
                "ranges": [_range(1), _range(2)],
                "earliest_reachable": "2020-01-01T00:00:00Z",
            },
        )
    )

    _content, structured = await mcp.call_tool("describe_coverage", {"symbol": "US100"})

    assert len(structured["ranges"]) == 2
    assert structured["earliest_reachable"] == "2020-01-01T00:00:00Z"
    assert structured["omitted_ranges"] == 0
    await upstream.aclose()


@respx.mock
async def test_coverage_beyond_the_limit_is_truncated_and_named(server) -> None:
    mcp, upstream = server
    ranges = [_range(day) for day in range(1, 26)]  # 25 ranges, limit is 20
    respx.get(f"{BASE}/coverage/US100").mock(
        return_value=httpx.Response(
            200,
            json={
                "symbol": "US100",
                "resolution": "MINUTE",
                "ranges": ranges,
                "earliest_reachable": None,
            },
        )
    )

    _content, structured = await mcp.call_tool("describe_coverage", {"symbol": "US100"})

    assert len(structured["ranges"]) == 20
    assert structured["omitted_ranges"] == 5
    assert any("omitted" in note for note in structured["notes"])
    # the most recent ranges are the ones kept
    assert structured["ranges"][0]["from"].startswith("2026-01-25")
    await upstream.aclose()


@respx.mock
async def test_no_coverage_for_untracked_pair(server) -> None:
    mcp, upstream = server
    respx.get(f"{BASE}/coverage/US100").mock(
        return_value=httpx.Response(
            200,
            json={
                "symbol": "US100",
                "resolution": "MINUTE",
                "ranges": [],
                "earliest_reachable": None,
            },
        )
    )
    respx.get(f"{BASE}/pairs").mock(return_value=httpx.Response(200, json=[]))

    _content, structured = await mcp.call_tool("describe_coverage", {"symbol": "US100"})

    assert structured["ranges"] == []
    assert any("nobody is collecting it" in note for note in structured["notes"])
    await upstream.aclose()
