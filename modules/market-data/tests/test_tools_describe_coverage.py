from __future__ import annotations

from datetime import UTC, datetime

from tools_double import coverage_range, tracked


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
