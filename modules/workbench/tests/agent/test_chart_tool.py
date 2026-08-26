"""The module's own tool: what it accepts, what it refuses, and what it leaves behind. The market-mcp
stand-in answers with the same JSON the real server's typed tools serialize."""

from __future__ import annotations

import json

import pytest

from agent import store
from agent.models import ChartIndicator, ChartSnapshot
from agent.tools import ToolOutcome, ToolOutcomeKind
from agent.tools.chart import ChartTool

pytestmark = pytest.mark.db

CATALOGUE = {
    "algorithm_version": 1,
    "group": None,
    "indicators": [
        {
            "id": "ema",
            "name": "Exponential Moving Average",
            "group": "averages",
            "output": "lines",
            "aliases": [],
            "params": [{"name": "period", "type": "int", "default": 20, "min": 2, "max": 5000}],
        },
        {
            "id": "range_gap",
            "name": "Range Gap",
            "group": "zones",
            "output": "zones",
            "aliases": ["FVG"],
            "params": [],
        },
    ],
}

PAIRS = [
    {
        "symbol": "US100",
        "resolution": "MINUTE_5",
        "collection": "running",
        "candle_count": 10,
        "latest_candle_age_seconds": 3.0,
    },
    {
        "symbol": "US100",
        "resolution": "HOUR",
        "collection": "running",
        "candle_count": 10,
        "latest_candle_age_seconds": 3.0,
    },
    {
        "symbol": "GOLD",
        "resolution": "MINUTE_5",
        "collection": "running",
        "candle_count": 10,
        "latest_candle_age_seconds": 3.0,
    },
]


class FakeToolServer:
    """Answers the two reads `chart.py` makes, in the shape market-mcp answers them."""

    configured = True

    def __init__(self, *, failing: str | None = None) -> None:
        self.seen: list[tuple[str, dict]] = []
        self._failing = failing

    async def call(self, name: str, arguments: dict) -> ToolOutcome:
        self.seen.append((name, arguments))
        if name == self._failing:
            return ToolOutcome(ToolOutcomeKind.UNAVAILABLE, "market-mcp did not answer", 7)
        if name == "list_indicators":
            return ToolOutcome(ToolOutcomeKind.OK, json.dumps(CATALOGUE), 3)
        if name == "list_tracked_pairs":
            return ToolOutcome(ToolOutcomeKind.OK, json.dumps(PAIRS), 3)
        raise AssertionError(f"the chart tool asked for an unexpected tool: {name}")


async def _session(db):
    return await store.create_session(db, owner_principal="op-1", model_id="gpt-5.6-luna")


def _tool(pool, server=None) -> ChartTool:
    return ChartTool(pool, server if server is not None else FakeToolServer())  # pyright: ignore[reportArgumentType]


async def test_a_full_set_is_recorded_as_one_command(db, pool) -> None:
    session = await _session(db)

    outcome = await _tool(pool).call(
        {
            "symbol": "US100",
            "resolution": "HOUR",
            "indicators": [
                {"id": "ema", "params": {"period": 20}, "color": "--color-accent"},
                {"id": "ema", "params": {"period": 200}},
            ],
        },
        session_id=session.id,
    )

    assert outcome.kind is ToolOutcomeKind.OK
    command = await store.chart_state_after(db, sequence=0)
    assert command is not None
    assert (command.symbol, command.resolution) == ("US100", "HOUR")
    assert command.indicators == [
        ChartIndicator(id="ema", params={"period": 20}, color="--color-accent"),
        ChartIndicator(id="ema", params={"period": 200}, color=None),
    ]


async def test_one_field_alone_says_nothing_about_the_others(db, pool) -> None:
    session = await _session(db)

    outcome = await _tool(pool).call({"resolution": "HOUR"}, session_id=session.id)

    assert outcome.kind is ToolOutcomeKind.OK
    command = await store.chart_state_after(db, sequence=0)
    assert command is not None
    assert command.symbol is None
    assert command.indicators is None
    assert command.resolution == "HOUR"


async def test_an_empty_command_is_refused(db, pool) -> None:
    session = await _session(db)

    outcome = await _tool(pool).call({}, session_id=session.id)

    assert outcome.kind is ToolOutcomeKind.REFUSED
    assert "at least one" in outcome.text
    assert await store.chart_state_after(db, sequence=0) is None


async def test_an_unknown_indicator_is_refused_and_nothing_is_written(db, pool) -> None:
    session = await _session(db)

    outcome = await _tool(pool).call(
        {
            "indicators": [
                {"id": "ema", "params": {"period": 20}},
                {"id": "supertrend"},
                {"id": "range_gap"},
            ]
        },
        session_id=session.id,
    )

    assert outcome.kind is ToolOutcomeKind.REFUSED
    assert "supertrend" in outcome.text
    # Not two of the three drawn: the command is written whole or not at all.
    assert await store.chart_state_after(db, sequence=0) is None


async def test_a_parameter_out_of_range_names_the_range(db, pool) -> None:
    session = await _session(db)

    outcome = await _tool(pool).call(
        {"indicators": [{"id": "ema", "params": {"period": 1}}]}, session_id=session.id
    )

    assert outcome.kind is ToolOutcomeKind.REFUSED
    assert "[2.0, 5000.0]" in outcome.text or "[2, 5000]" in outcome.text
    assert await store.chart_state_after(db, sequence=0) is None


async def test_a_parameter_the_indicator_does_not_have_is_refused(db, pool) -> None:
    session = await _session(db)

    outcome = await _tool(pool).call(
        {"indicators": [{"id": "ema", "params": {"length": 20}}]}, session_id=session.id
    )

    assert outcome.kind is ToolOutcomeKind.REFUSED
    assert "length" in outcome.text
    assert "period" in outcome.text


async def test_a_symbol_the_archive_does_not_collect_is_refused_with_the_ones_it_does(
    db, pool
) -> None:
    session = await _session(db)

    outcome = await _tool(pool).call({"symbol": "TSLA"}, session_id=session.id)

    assert outcome.kind is ToolOutcomeKind.REFUSED
    assert "TSLA" in outcome.text
    assert "US100" in outcome.text and "GOLD" in outcome.text
    assert await store.chart_state_after(db, sequence=0) is None


async def test_a_resolution_that_symbol_is_not_collected_in_is_refused(db, pool) -> None:
    session = await _session(db)

    outcome = await _tool(pool).call(
        {"symbol": "GOLD", "resolution": "HOUR"}, session_id=session.id
    )

    assert outcome.kind is ToolOutcomeKind.REFUSED
    assert "HOUR" in outcome.text and "MINUTE_5" in outcome.text


async def test_a_symbol_only_command_is_checked_against_the_chart_s_current_interval(
    db, pool
) -> None:
    session = await _session(db)

    outcome = await _tool(pool).call(
        {"symbol": "GOLD"},
        session_id=session.id,
        chart=ChartSnapshot(symbol="US100", resolution="HOUR"),
    )

    assert outcome.kind is ToolOutcomeKind.REFUSED
    assert "HOUR" in outcome.text and "GOLD" in outcome.text
    assert await store.chart_state_after(db, sequence=0) is None


async def test_a_symbol_only_command_is_accepted_when_the_current_interval_fits(
    db, pool
) -> None:
    session = await _session(db)

    outcome = await _tool(pool).call(
        {"symbol": "GOLD"},
        session_id=session.id,
        chart=ChartSnapshot(symbol="US100", resolution="MINUTE_5"),
    )

    assert outcome.kind is ToolOutcomeKind.OK
    command = await store.chart_state_after(db, sequence=0)
    assert command is not None
    assert command.symbol == "GOLD"


async def test_a_colour_the_chart_cannot_draw_is_refused(db, pool) -> None:
    session = await _session(db)

    outcome = await _tool(pool).call(
        {"indicators": [{"id": "ema", "color": "#ff00ff"}]}, session_id=session.id
    )

    assert outcome.kind is ToolOutcomeKind.REFUSED
    assert "--color-accent" in outcome.text


async def test_without_a_tool_server_it_refuses_rather_than_writing_blind(db, pool) -> None:
    session = await _session(db)

    outcome = await ChartTool(pool, None).call({"symbol": "US100"}, session_id=session.id)

    assert outcome.kind is ToolOutcomeKind.REFUSED
    assert "left alone" in outcome.text
    assert await store.chart_state_after(db, sequence=0) is None


async def test_an_archive_that_does_not_answer_is_not_a_reason_to_guess(db, pool) -> None:
    session = await _session(db)
    server = FakeToolServer(failing="list_tracked_pairs")

    outcome = await _tool(pool, server).call({"symbol": "US100"}, session_id=session.id)

    assert outcome.kind is ToolOutcomeKind.REFUSED
    assert "Nothing was changed" in outcome.text
    assert await store.chart_state_after(db, sequence=0) is None


async def test_drawing_none_is_sayable(db, pool) -> None:
    session = await _session(db)

    outcome = await _tool(pool).call({"indicators": []}, session_id=session.id)

    assert outcome.kind is ToolOutcomeKind.OK
    command = await store.chart_state_after(db, sequence=0)
    assert command is not None
    assert command.indicators == []
