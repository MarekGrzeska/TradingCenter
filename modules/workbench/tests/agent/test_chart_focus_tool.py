"""The `focus` field of `set_chart`: the three shapes it takes, what it refuses, and what
it writes.

specs/agent-chart-control (delta, `agent-chart-navigation`), "Narzędzie ustawia zawartość
aktywnego slotu" and "Odmowa narzędzia nazywa, co poprawić".
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from agent import store
from agent.models import ChartFocus
from agent.tools import ToolOutcomeKind
from agent.tools.chart import ChartTool

pytestmark = pytest.mark.db


async def _session(db):
    return await store.create_session(db, owner_principal="op-1", model_id="gpt-5.6-luna")


def _tool(pool) -> ChartTool:
    # No tool server passed: none of these calls sets a symbol, an interval or an
    # indicator, so none of them needs the archive to check anything.
    return ChartTool(pool, None)


async def test_a_range_moves_the_operator_to_a_date(db, pool) -> None:
    session = await _session(db)

    outcome = await _tool(pool).call(
        {"focus": {"from": "2026-01-03T00:00:00Z", "to": "2026-01-04T00:00:00Z"}},
        session_id=session.id,
    )

    assert outcome.kind is ToolOutcomeKind.OK
    command = await store.chart_state_after(db, sequence=0)
    assert command is not None
    assert command.focus == ChartFocus(
        from_=datetime(2026, 1, 3, tzinfo=UTC), to=datetime(2026, 1, 4, tzinfo=UTC)
    )


async def test_last_bars_zooms_to_the_end_of_the_series(db, pool) -> None:
    session = await _session(db)

    outcome = await _tool(pool).call({"focus": {"last_bars": 100}}, session_id=session.id)

    assert outcome.kind is ToolOutcomeKind.OK
    command = await store.chart_state_after(db, sequence=0)
    assert command is not None
    assert command.focus == ChartFocus(last_bars=100)


async def test_a_point_with_bars_is_accepted(db, pool) -> None:
    session = await _session(db)

    outcome = await _tool(pool).call(
        {"focus": {"around": "2026-01-03T12:00:00Z", "bars": 50}}, session_id=session.id
    )

    assert outcome.kind is ToolOutcomeKind.OK
    command = await store.chart_state_after(db, sequence=0)
    assert command is not None
    assert command.focus is not None
    assert command.focus.bars == 50


async def test_a_focus_only_call_is_something_to_set(db, pool) -> None:
    # Task 2.4: none of `symbol`, `resolution`, `indicators` is present, but `focus`
    # alone is enough — it must not be refused as "nothing to set".
    session = await _session(db)

    outcome = await _tool(pool).call({"focus": {"last_bars": 20}}, session_id=session.id)

    assert outcome.kind is ToolOutcomeKind.OK
    assert "focus" in outcome.text


async def test_a_focus_only_call_needs_no_archive(db, pool) -> None:
    # design.md, "Sprawdzenie kadru nie wymaga dodatkowego odczytu z archiwum" — a focus
    # is checked entirely without a read, so a call naming only a focus must succeed even
    # when there is no tool server to check a symbol or an indicator against.
    session = await _session(db)

    outcome = await ChartTool(pool, None).call(
        {"focus": {"last_bars": 20}}, session_id=session.id
    )

    assert outcome.kind is ToolOutcomeKind.OK


async def test_still_nothing_to_set_without_any_of_the_four_fields(db, pool) -> None:
    session = await _session(db)

    outcome = await _tool(pool).call({}, session_id=session.id)

    assert outcome.kind is ToolOutcomeKind.REFUSED
    assert "focus" in outcome.text
    assert await store.chart_state_after(db, sequence=0) is None


async def test_two_shapes_at_once_is_refused(db, pool) -> None:
    session = await _session(db)

    outcome = await _tool(pool).call(
        {"focus": {"from": "2026-01-03T00:00:00Z", "to": "2026-01-04T00:00:00Z", "last_bars": 50}},
        session_id=session.id,
    )

    assert outcome.kind is ToolOutcomeKind.REFUSED
    assert "exactly one way" in outcome.text
    assert await store.chart_state_after(db, sequence=0) is None


async def test_no_shape_at_all_is_refused(db, pool) -> None:
    session = await _session(db)

    outcome = await _tool(pool).call({"focus": {}}, session_id=session.id)

    assert outcome.kind is ToolOutcomeKind.REFUSED
    assert "exactly one way" in outcome.text


async def test_an_inverted_range_names_both_ends(db, pool) -> None:
    session = await _session(db)

    outcome = await _tool(pool).call(
        {"focus": {"from": "2026-01-04T00:00:00Z", "to": "2026-01-03T00:00:00Z"}},
        session_id=session.id,
    )

    assert outcome.kind is ToolOutcomeKind.REFUSED
    assert "earlier than" in outcome.text
    assert "2026-01-04T00:00:00Z" in outcome.text
    assert "2026-01-03T00:00:00Z" in outcome.text
    assert await store.chart_state_after(db, sequence=0) is None


async def test_an_equal_range_is_refused(db, pool) -> None:
    session = await _session(db)

    outcome = await _tool(pool).call(
        {"focus": {"from": "2026-01-03T00:00:00Z", "to": "2026-01-03T00:00:00Z"}},
        session_id=session.id,
    )

    assert outcome.kind is ToolOutcomeKind.REFUSED
    assert "earlier than" in outcome.text


@pytest.mark.parametrize("field", ["bars", "last_bars"])
async def test_a_bar_count_below_the_floor_names_the_bounds(db, pool, field) -> None:
    session = await _session(db)
    focus = {"last_bars": 5} if field == "last_bars" else {"around": "2026-01-03T00:00:00Z", "bars": 5}

    outcome = await _tool(pool).call({"focus": focus}, session_id=session.id)

    assert outcome.kind is ToolOutcomeKind.REFUSED
    assert "10" in outcome.text
    assert "1000" in outcome.text


@pytest.mark.parametrize("field", ["bars", "last_bars"])
async def test_a_bar_count_above_the_ceiling_names_the_bounds(db, pool, field) -> None:
    session = await _session(db)
    focus = (
        {"last_bars": 5000}
        if field == "last_bars"
        else {"around": "2026-01-03T00:00:00Z", "bars": 5000}
    )

    outcome = await _tool(pool).call({"focus": focus}, session_id=session.id)

    assert outcome.kind is ToolOutcomeKind.REFUSED
    assert "10" in outcome.text
    assert "1000" in outcome.text


async def test_a_range_entirely_in_the_future_is_refused(db, pool) -> None:
    session = await _session(db)

    outcome = await _tool(pool).call(
        {"focus": {"from": "2099-01-03T00:00:00Z", "to": "2099-01-04T00:00:00Z"}},
        session_id=session.id,
    )

    assert outcome.kind is ToolOutcomeKind.REFUSED
    assert "future" in outcome.text
    assert await store.chart_state_after(db, sequence=0) is None


async def test_a_point_in_the_future_is_refused(db, pool) -> None:
    session = await _session(db)

    outcome = await _tool(pool).call(
        {"focus": {"around": "2099-01-03T00:00:00Z", "bars": 50}}, session_id=session.id
    )

    assert outcome.kind is ToolOutcomeKind.REFUSED
    assert "future" in outcome.text


async def test_a_naive_timestamp_is_refused(db, pool) -> None:
    session = await _session(db)

    outcome = await _tool(pool).call(
        {"focus": {"from": "2026-01-03T00:00:00", "to": "2026-01-04T00:00:00"}},
        session_id=session.id,
    )

    assert outcome.kind is ToolOutcomeKind.REFUSED
    assert "UTC offset" in outcome.text


async def test_an_unparseable_timestamp_is_refused(db, pool) -> None:
    session = await _session(db)

    outcome = await _tool(pool).call(
        {"focus": {"from": "not a date", "to": "2026-01-04T00:00:00Z"}}, session_id=session.id
    )

    assert outcome.kind is ToolOutcomeKind.REFUSED
    assert "not a valid ISO 8601 timestamp" in outcome.text


async def test_a_range_without_its_other_half_is_refused(db, pool) -> None:
    session = await _session(db)

    outcome = await _tool(pool).call(
        {"focus": {"from": "2026-01-03T00:00:00Z"}}, session_id=session.id
    )

    assert outcome.kind is ToolOutcomeKind.REFUSED
    assert "together" in outcome.text


async def test_a_point_without_bars_is_refused(db, pool) -> None:
    session = await _session(db)

    outcome = await _tool(pool).call(
        {"focus": {"around": "2026-01-03T00:00:00Z"}}, session_id=session.id
    )

    assert outcome.kind is ToolOutcomeKind.REFUSED
    assert "together" in outcome.text
