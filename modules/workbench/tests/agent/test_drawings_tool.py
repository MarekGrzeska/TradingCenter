"""The two drawing tools against a real database: what lands, what comes back, what does not. The
market-mcp stand-in answers with the same JSON the real server's typed tools serialize.

Argument validation is not here: it refuses before the pool is touched, so the two dozen permutations that
used to sit in this file are one parameterised test in `test_drawings_refusals.py` now."""

from __future__ import annotations

import json

import pytest

from agent import store
from agent.models import ChartLevel, ChartTrendline, ChartZone
from agent.store import MAX_DRAWINGS_PER_SYMBOL
from agent.tools import ToolOutcome, ToolOutcomeKind
from agent.tools.drawings import DrawOnChartTool, ListChartDrawingsTool

pytestmark = pytest.mark.db

PAIRS = [
    {
        "symbol": "US100",
        "resolution": "MINUTE_5",
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

A_LEVEL = {"kind": "level", "price": 21500.0, "label": "weekly high"}


class FakeToolServer:
    """Answers the one read `drawings.py` makes, in the shape market-mcp answers it."""

    configured = True

    def __init__(self, *, failing: bool = False) -> None:
        self.seen: list[tuple[str, dict]] = []
        self._failing = failing

    async def call(self, name: str, arguments: dict) -> ToolOutcome:
        self.seen.append((name, arguments))
        if self._failing:
            return ToolOutcome(ToolOutcomeKind.UNAVAILABLE, "market-mcp did not answer", 7)
        if name == "list_tracked_pairs":
            return ToolOutcome(ToolOutcomeKind.OK, json.dumps(PAIRS), 3)
        raise AssertionError(f"the drawing tool asked for an unexpected tool: {name}")


async def _session(db):
    return await store.create_session(db, owner_principal="op-1", model_id="gpt-5.6-luna")


def _draw(pool, server=None) -> DrawOnChartTool:
    return DrawOnChartTool(pool, server if server is not None else FakeToolServer())  # pyright: ignore[reportArgumentType]


def _read(pool) -> ListChartDrawingsTool:
    return ListChartDrawingsTool(pool)



async def test_two_levels_in_one_call_both_land(db, pool) -> None:
    session = await _session(db)

    outcome = await _draw(pool).call(
        {
            "symbol": "US100",
            "add": [
                {"kind": "level", "price": 21500.0, "label": "resistance"},
                {"kind": "level", "price": 21000.0, "label": "support", "color": "--color-drawing-2"},
            ],
        },
        session_id=session.id,
    )

    assert outcome.kind is ToolOutcomeKind.OK
    drawings = await store.list_drawings(db, symbol="US100")
    assert [d.geometry.price for d in drawings] == [21500.0, 21000.0]  # pyright: ignore[reportAttributeAccessIssue]
    assert all(d.session_id == session.id for d in drawings)
    # specs/agent-chart-drawings, "Kolor z palety rysunków" — a token from the drawing
    # palette is kept as written.
    assert [d.geometry.color for d in drawings] == [None, "--color-drawing-2"]


async def test_all_three_shapes_are_drawable(db, pool) -> None:
    outcome = await _draw(pool).call(
        {
            "symbol": "US100",
            "add": [
                {"kind": "level", "price": 21500.0, "at": "2026-01-03T09:00:00Z"},
                {"kind": "zone", "top": 21600.0, "bottom": 21550.0, "from": "2026-01-03T09:00:00Z"},
                {
                    "kind": "trendline",
                    "a": {"time": "2026-01-03T09:00:00Z", "price": 21000.0},
                    "b": {"time": "2026-01-04T09:00:00Z", "price": 21400.0},
                },
            ],
        },
        session_id=(await _session(db)).id,
    )

    assert outcome.kind is ToolOutcomeKind.OK
    drawings = await store.list_drawings(db, symbol="US100")
    assert [type(d.geometry) for d in drawings] == [ChartLevel, ChartZone, ChartTrendline]
    # A zone open-ended in time is a zone: both of its moments are optional.
    assert drawings[1].geometry.to is None  # pyright: ignore[reportAttributeAccessIssue]


async def test_adding_does_not_remove_what_is_already_there(db, pool) -> None:
    """Incremental, not declarative — the one place this module inverts `set_chart`
    (specs/agent-chart-drawings, "Agent nie kasuje przez pominięcie")."""
    session = await _session(db)
    await store.add_drawings(
        db,
        session_id=session.id,
        symbol="US100",
        geometries=[ChartLevel(price=p) for p in (21100.0, 21200.0, 21300.0)],
    )

    outcome = await _draw(pool).call(
        {"symbol": "US100", "add": [{"kind": "level", "price": 21400.0}]},
        session_id=session.id,
    )

    assert outcome.kind is ToolOutcomeKind.OK
    assert len(await store.list_drawings(db, symbol="US100")) == 4


async def test_a_removal_and_an_addition_travel_together(db, pool) -> None:
    """"Move the resistance ten points up" is one call, not two — the chart never shows
    the instrument without its level in between (design.md, "Dwa narzędzia")."""
    session = await _session(db)
    [old] = await store.add_drawings(
        db, session_id=session.id, symbol="US100", geometries=[ChartLevel(price=21500.0)]
    )

    outcome = await _draw(pool).call(
        {
            "symbol": "US100",
            "add": [{"kind": "level", "price": 21510.0}],
            "remove": [old.id],
        },
        session_id=session.id,
    )

    assert outcome.kind is ToolOutcomeKind.OK
    [standing] = await store.list_drawings(db, symbol="US100")
    assert standing.geometry.price == 21510.0  # pyright: ignore[reportAttributeAccessIssue]



async def test_a_symbol_the_archive_does_not_collect_is_refused_with_the_ones_it_does(
    db, pool
) -> None:
    outcome = await _draw(pool).call(
        {"symbol": "EURUSD", "add": [A_LEVEL]}, session_id=(await _session(db)).id
    )

    assert outcome.kind is ToolOutcomeKind.REFUSED
    assert "GOLD" in outcome.text and "US100" in outcome.text
    assert await store.list_drawings(db, symbol="EURUSD") == []


async def test_without_a_tool_server_it_refuses_rather_than_drawing_blind(db, pool) -> None:
    outcome = await DrawOnChartTool(pool, None).call(
        {"symbol": "US100", "add": [A_LEVEL]}, session_id=(await _session(db)).id
    )

    assert outcome.kind is ToolOutcomeKind.REFUSED
    assert await store.list_drawings(db, symbol="US100") == []


async def test_an_archive_that_does_not_answer_is_not_a_reason_to_guess(db, pool) -> None:
    outcome = await _draw(pool, FakeToolServer(failing=True)).call(
        {"symbol": "US100", "add": [A_LEVEL]}, session_id=(await _session(db)).id
    )

    assert outcome.kind is ToolOutcomeKind.REFUSED
    assert await store.list_drawings(db, symbol="US100") == []


async def test_the_ceiling_refuses_the_whole_call(db, pool) -> None:
    session = await _session(db)
    await store.add_drawings(
        db,
        session_id=session.id,
        symbol="US100",
        geometries=[ChartLevel(price=float(20000 + n)) for n in range(MAX_DRAWINGS_PER_SYMBOL - 1)],
    )

    outcome = await _draw(pool).call(
        {
            "symbol": "US100",
            "add": [{"kind": "level", "price": 21500.0}, {"kind": "level", "price": 21600.0}],
        },
        session_id=session.id,
    )

    assert outcome.kind is ToolOutcomeKind.REFUSED
    assert str(MAX_DRAWINGS_PER_SYMBOL) in outcome.text
    assert len(await store.list_drawings(db, symbol="US100")) == MAX_DRAWINGS_PER_SYMBOL - 1


async def test_removing_an_id_that_is_not_there_says_so(db, pool) -> None:
    session = await _session(db)
    [standing] = await store.add_drawings(
        db, session_id=session.id, symbol="US100", geometries=[ChartLevel(price=21500.0)]
    )

    outcome = await _draw(pool).call(
        {"symbol": "US100", "remove": [standing.id + 99]}, session_id=session.id
    )

    assert outcome.kind is ToolOutcomeKind.REFUSED
    assert str(standing.id + 99) in outcome.text
    assert [d.id for d in await store.list_drawings(db, symbol="US100")] == [standing.id]


async def test_a_removal_that_names_one_missing_id_takes_back_the_others(db, pool) -> None:
    """The transaction is the whole call: a removal of two, one of which is not there,
    leaves both where they were."""
    session = await _session(db)
    written = await store.add_drawings(
        db,
        session_id=session.id,
        symbol="US100",
        geometries=[ChartLevel(price=21500.0), ChartLevel(price=21400.0)],
    )

    outcome = await _draw(pool).call(
        {"symbol": "US100", "remove": [written[0].id, written[1].id + 99]},
        session_id=session.id,
    )

    assert outcome.kind is ToolOutcomeKind.REFUSED
    assert len(await store.list_drawings(db, symbol="US100")) == 2


async def test_an_id_belonging_to_another_instrument_is_not_removable(db, pool) -> None:
    session = await _session(db)
    [elsewhere] = await store.add_drawings(
        db, session_id=session.id, symbol="GOLD", geometries=[ChartLevel(price=2400.0)]
    )

    outcome = await _draw(pool).call(
        {"symbol": "US100", "remove": [elsewhere.id]}, session_id=session.id
    )

    assert outcome.kind is ToolOutcomeKind.REFUSED
    assert len(await store.list_drawings(db, symbol="GOLD")) == 1



async def test_the_read_carries_ids_shapes_and_labels(db, pool) -> None:
    session = await _session(db)
    written = await store.add_drawings(
        db,
        session_id=session.id,
        symbol="US100",
        geometries=[
            ChartLevel(price=21500.0, label="weekly high", color="--color-up"),
            ChartZone(top=21600.0, bottom=21550.0),
        ],
    )

    outcome = await _read(pool).call({"symbol": "US100"})

    assert outcome.kind is ToolOutcomeKind.OK
    payload = json.loads(outcome.text)
    assert payload["symbol"] == "US100"
    assert [d["id"] for d in payload["drawings"]] == [w.id for w in written]
    assert payload["drawings"][0] == {
        "id": written[0].id,
        "kind": "level",
        "price": 21500.0,
        "label": "weekly high",
        "color": "--color-up",
        "hidden": False,
        "created_at": written[0].created_at.isoformat(),
    }
    assert payload["drawings"][1]["top"] == 21600.0
    assert payload["drawings"][1]["bottom"] == 21550.0


async def test_the_read_does_not_show_another_instruments_drawings(db, pool) -> None:
    session = await _session(db)
    await store.add_drawings(
        db, session_id=session.id, symbol="GOLD", geometries=[ChartLevel(price=2400.0)]
    )

    outcome = await _read(pool).call({"symbol": "US100"})

    assert json.loads(outcome.text)["drawings"] == []


async def test_read_then_remove_uses_the_same_id(db, pool) -> None:
    session = await _session(db)
    await store.add_drawings(
        db,
        session_id=session.id,
        symbol="US100",
        geometries=[ChartLevel(price=21500.0), ChartLevel(price=21400.0)],
    )

    read = json.loads((await _read(pool).call({"symbol": "US100"})).text)
    first_id = read["drawings"][0]["id"]
    outcome = await _draw(pool).call({"symbol": "US100", "remove": [first_id]}, session_id=session.id)

    assert outcome.kind is ToolOutcomeKind.OK
    remaining = await store.list_drawings(db, symbol="US100")
    assert [d.id for d in remaining] == [read["drawings"][1]["id"]]



async def test_hiding_takes_a_drawing_off_the_chart_and_keeps_it(db, pool) -> None:
    """specs/agent-chart-drawings, "Agent gasi rysunek zamiast go kasować"."""
    session = await _session(db)
    [standing] = await store.add_drawings(
        db,
        session_id=session.id,
        symbol="US100",
        geometries=[ChartLevel(price=21500.0, label="weekly high")],
    )

    outcome = await _draw(pool).call({"symbol": "US100", "hide": [standing.id]}, session_id=session.id)

    assert outcome.kind is ToolOutcomeKind.OK
    [after] = await store.list_drawings(db, symbol="US100")
    assert after.hidden is True
    # Everything else is exactly what it was — that is the whole difference from removing,
    # and the confirmation the operator reads back has to say which of the two happened.
    assert after.id == standing.id
    assert after.created_at == standing.created_at
    assert after.geometry == standing.geometry
    assert "hid" in outcome.text and "removed" not in outcome.text


async def test_showing_gives_back_the_same_drawing(db, pool) -> None:
    session = await _session(db)
    [standing] = await store.add_drawings(
        db, session_id=session.id, symbol="US100", geometries=[ChartLevel(price=21500.0)]
    )
    await _draw(pool).call({"symbol": "US100", "hide": [standing.id]}, session_id=session.id)

    outcome = await _draw(pool).call({"symbol": "US100", "show": [standing.id]}, session_id=session.id)

    assert outcome.kind is ToolOutcomeKind.OK
    [after] = await store.list_drawings(db, symbol="US100")
    assert after.hidden is False
    assert after.geometry == standing.geometry


async def test_hiding_an_id_that_is_not_there_takes_back_the_others(db, pool) -> None:
    """The transaction is the whole call, the same as for a removal
    (specs/agent-chart-drawings, "Gaszenie identyfikatora, którego nie ma")."""
    session = await _session(db)
    written = await store.add_drawings(
        db,
        session_id=session.id,
        symbol="US100",
        geometries=[ChartLevel(price=21500.0), ChartLevel(price=21400.0)],
    )

    outcome = await _draw(pool).call(
        {"symbol": "US100", "hide": [written[0].id, written[1].id + 99]}, session_id=session.id
    )

    assert outcome.kind is ToolOutcomeKind.REFUSED
    assert str(written[1].id + 99) in outcome.text
    assert [d.hidden for d in await store.list_drawings(db, symbol="US100")] == [False, False]


async def test_hiding_does_not_touch_what_it_was_not_told_to(db, pool) -> None:
    """specs/agent-chart-drawings, "Agent nie gasi przez pominięcie"."""
    session = await _session(db)
    written = await store.add_drawings(
        db,
        session_id=session.id,
        symbol="US100",
        geometries=[
            ChartLevel(price=21500.0),
            ChartLevel(price=21400.0),
            ChartLevel(price=21300.0),
        ],
    )

    await _draw(pool).call({"symbol": "US100", "hide": [written[0].id]}, session_id=session.id)

    assert [d.hidden for d in await store.list_drawings(db, symbol="US100")] == [True, False, False]


async def test_hiding_and_drawing_travel_together(db, pool) -> None:
    """"Hide the old resistance and put up the new one" is one move, not two — the reason hiding went into
    this tool rather than beside it."""
    session = await _session(db)
    [old] = await store.add_drawings(
        db, session_id=session.id, symbol="US100", geometries=[ChartLevel(price=21500.0)]
    )

    outcome = await _draw(pool).call(
        {"symbol": "US100", "hide": [old.id], "add": [{"kind": "level", "price": 21600.0}]},
        session_id=session.id,
    )

    assert outcome.kind is ToolOutcomeKind.OK
    standing = await store.list_drawings(db, symbol="US100")
    assert [(d.geometry.price, d.hidden) for d in standing] == [(21500.0, True), (21600.0, False)]


async def test_hidden_drawings_still_count_towards_the_ceiling(db, pool) -> None:
    """The ceiling is about the record, not about how crowded the screen looks; one that
    can be walked around by hiding is not a ceiling (proposal.md, "Impact")."""
    session = await _session(db)
    written = await store.add_drawings(
        db,
        session_id=session.id,
        symbol="US100",
        geometries=[ChartLevel(price=20000.0 + n) for n in range(MAX_DRAWINGS_PER_SYMBOL)],
    )
    await _draw(pool).call(
        {"symbol": "US100", "hide": [d.id for d in written[:50]]}, session_id=session.id
    )

    outcome = await _draw(pool).call(
        {"symbol": "US100", "add": [{"kind": "level", "price": 21999.0}]}, session_id=session.id
    )

    assert outcome.kind is ToolOutcomeKind.REFUSED
    assert str(MAX_DRAWINGS_PER_SYMBOL) in outcome.text


async def test_the_read_says_which_drawings_are_hidden(db, pool) -> None:
    """specs/agent-chart-drawings, "Odczyt mówi, który rysunek jest zgaszony"."""
    session = await _session(db)
    written = await store.add_drawings(
        db,
        session_id=session.id,
        symbol="US100",
        geometries=[ChartLevel(price=21500.0), ChartLevel(price=21400.0)],
    )
    await _draw(pool).call({"symbol": "US100", "hide": [written[0].id]}, session_id=session.id)

    outcome = await _read(pool).call({"symbol": "US100"})

    assert [d["hidden"] for d in json.loads(outcome.text)["drawings"]] == [True, False]
