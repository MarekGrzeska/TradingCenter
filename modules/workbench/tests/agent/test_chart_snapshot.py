"""What the turn's chart snapshot says, and what it says nothing about.

specs/agent-chat, "Tura wie, co terminal właśnie rysuje" — the visible span is optional on
its own, and its absence must not read as "no candles are visible", only as "unknown".
"""

from __future__ import annotations

from datetime import UTC, datetime

from agent.contract import ChartSnapshotIn
from agent.models import ChartIndicator, ChartSnapshot


def test_as_context_names_the_visible_span() -> None:
    snapshot = ChartSnapshot(
        symbol="US100",
        resolution="MINUTE_5",
        indicators=[ChartIndicator(id="ema", params={"period": 20})],
        visible_from=datetime(2026, 1, 3, 9, 0, tzinfo=UTC),
        visible_to=datetime(2026, 1, 3, 17, 0, tzinfo=UTC),
    )

    sentence = snapshot.as_context()

    assert "2026-01-03T09:00:00+00:00" in sentence
    assert "2026-01-03T17:00:00+00:00" in sentence


def test_as_context_omits_the_span_when_absent() -> None:
    snapshot = ChartSnapshot(symbol="US100", resolution="MINUTE_5", indicators=[])

    sentence = snapshot.as_context()

    assert "visible time span" not in sentence


def test_as_context_omits_the_span_when_only_one_half_is_known() -> None:
    # A consumer that draws but cannot say where the frame ends must not have a fragment
    # invented for it — half a span is not a span.
    snapshot = ChartSnapshot(
        symbol="US100",
        resolution="MINUTE_5",
        indicators=[],
        visible_from=datetime(2026, 1, 3, 9, 0, tzinfo=UTC),
    )

    sentence = snapshot.as_context()

    assert "visible time span" not in sentence


def test_chart_snapshot_in_carries_the_visible_span_through() -> None:
    incoming = ChartSnapshotIn(
        symbol="US100",
        resolution="MINUTE_5",
        indicators=[],
        visible_from=datetime(2026, 1, 3, 9, 0, tzinfo=UTC),
        visible_to=datetime(2026, 1, 3, 17, 0, tzinfo=UTC),
    )

    snapshot = incoming.to_snapshot()

    assert snapshot.visible_from == datetime(2026, 1, 3, 9, 0, tzinfo=UTC)
    assert snapshot.visible_to == datetime(2026, 1, 3, 17, 0, tzinfo=UTC)


def test_chart_snapshot_in_without_the_span_behaves_as_before() -> None:
    incoming = ChartSnapshotIn(symbol="US100", resolution="MINUTE_5", indicators=[])

    snapshot = incoming.to_snapshot()

    assert snapshot.visible_from is None
    assert snapshot.visible_to is None
