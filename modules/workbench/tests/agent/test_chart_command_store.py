"""The chart-command log: one row per accepted command, a sequence the terminal can hold onto, and one
folded answer for whatever it missed."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from agent import store
from agent.models import ChartFocus, ChartIndicator

pytestmark = pytest.mark.db


async def _session(db, owner: str = "op-1"):
    return await store.create_session(db, owner_principal=owner, model_id="gpt-5.6-luna")


async def test_sequence_rises_across_sessions(db) -> None:
    # One chart, one cursor — a number that restarted per rozmowa would tell the terminal
    # nothing about what it has already applied.
    first_session = await _session(db)
    second_session = await _session(db, owner="op-2")

    first = await store.record_chart_command(
        db,
        session_id=first_session.id,
        symbol="US100",
        resolution=None,
        indicators=None,
        focus=None,
    )
    second = await store.record_chart_command(
        db,
        session_id=second_session.id,
        symbol=None,
        resolution="HOUR",
        indicators=None,
        focus=None,
    )

    assert second.sequence > first.sequence


async def test_indicators_survive_the_round_trip(db) -> None:
    session = await _session(db)
    written = await store.record_chart_command(
        db,
        session_id=session.id,
        symbol=None,
        resolution=None,
        indicators=[
            ChartIndicator(id="ema", params={"period": 20}, color="--color-accent"),
            ChartIndicator(id="ema", params={"period": 200}, color=None),
        ],
        focus=None,
    )

    read = await store.chart_state_after(db, sequence=written.sequence - 1)

    assert read is not None
    assert read.indicators == [
        ChartIndicator(id="ema", params={"period": 20}, color="--color-accent"),
        ChartIndicator(id="ema", params={"period": 200}, color=None),
    ]


async def test_nothing_newer_than_the_cursor_is_nothing(db) -> None:
    session = await _session(db)
    written = await store.record_chart_command(
        db, session_id=session.id, symbol="US100", resolution=None, indicators=None,
        focus=None,
    )

    assert await store.chart_state_after(db, sequence=written.sequence) is None
    # And asking twice says the same, because reading changes nothing here.
    assert await store.chart_state_after(db, sequence=written.sequence) is None


async def test_missed_commands_fold_into_one_answer(db) -> None:
    # The reason the answer is folded rather than "the newest row": the first command is the only one that
    # says anything about indicators, and a consumer that was away must not lose them.
    session = await _session(db)
    start = await store.record_chart_command(
        db,
        session_id=session.id,
        symbol="US100",
        resolution="MINUTE_5",
        indicators=[ChartIndicator(id="rsi", params={"period": 14})],
        focus=None,
    )
    await store.record_chart_command(
        db,
        session_id=session.id,
        symbol=None,
        resolution=None,
        indicators=[ChartIndicator(id="ema", params={"period": 50})],
        focus=None,
    )
    last = await store.record_chart_command(
        db, session_id=session.id, symbol="GOLD", resolution=None, indicators=None,
        focus=None,
    )

    folded = await store.chart_state_after(db, sequence=start.sequence - 1)

    assert folded is not None
    assert folded.sequence == last.sequence
    assert folded.symbol == "GOLD"
    # Neither of the later commands said anything about the resolution, so the first one's
    # still stands.
    assert folded.resolution == "MINUTE_5"
    assert folded.indicators == [ChartIndicator(id="ema", params={"period": 50})]


async def test_focus_survives_the_round_trip(db) -> None:
    session = await _session(db)
    around = datetime(2026, 1, 3, 12, 0, tzinfo=UTC)
    written = await store.record_chart_command(
        db,
        session_id=session.id,
        symbol=None,
        resolution=None,
        indicators=None,
        focus=ChartFocus(around=around, bars=200),
    )

    read = await store.chart_state_after(db, sequence=written.sequence - 1)

    assert read is not None
    assert read.focus == ChartFocus(around=around, bars=200)


async def test_a_command_with_only_a_focus_is_still_a_command(db) -> None:
    # The check constraint the migration widens: a row that sets nothing at all cannot
    # exist, but a focus-only command must not be rejected by it.
    session = await _session(db)
    written = await store.record_chart_command(
        db,
        session_id=session.id,
        symbol=None,
        resolution=None,
        indicators=None,
        focus=ChartFocus(last_bars=50),
    )

    read = await store.chart_state_after(db, sequence=written.sequence - 1)

    assert read is not None
    assert read.focus == ChartFocus(last_bars=50)


async def test_drawing_none_is_a_command_of_its_own(db) -> None:
    # `[]` says "draw no indicators"; null says "leave them alone". Collapsing the two
    # would make "clear the chart" unsayable.
    session = await _session(db)
    first = await store.record_chart_command(
        db,
        session_id=session.id,
        symbol=None,
        resolution=None,
        indicators=[ChartIndicator(id="ema", params={"period": 20})],
        focus=None,
    )
    await store.record_chart_command(
        db, session_id=session.id, symbol=None, resolution=None, indicators=[],
        focus=None,
    )

    folded = await store.chart_state_after(db, sequence=first.sequence - 1)

    assert folded is not None
    assert folded.indicators == []
