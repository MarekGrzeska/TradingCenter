"""The two drawing tools: what they accept, what they refuse, and what they leave behind.

specs/agent-chart-drawings, "Agent stawia i kasuje rysunki narzędziem", "Agent odczytuje
rysunki narzędziem" and "Odmowa rysowania nazywa, co poprawić". The market-mcp stand-in
answers with the same JSON the real server's typed tools serialize, which is what
`drawings.py` parses through `chart.read_json`.
"""

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


# --- what it draws -------------------------------------------------------------------


async def test_two_levels_in_one_call_both_land(db, pool) -> None:
    session = await _session(db)

    outcome = await _draw(pool).call(
        {
            "symbol": "US100",
            "add": [
                {"kind": "level", "price": 21500.0, "label": "resistance"},
                {"kind": "level", "price": 21000.0, "label": "support"},
            ],
        },
        session_id=session.id,
    )

    assert outcome.kind is ToolOutcomeKind.OK
    drawings = await store.list_drawings(db, symbol="US100")
    assert [d.geometry.price for d in drawings] == [21500.0, 21000.0]  # pyright: ignore[reportAttributeAccessIssue]
    assert all(d.session_id == session.id for d in drawings)


async def test_all_three_shapes_are_drawable(db, pool) -> None:
    session = await _session(db)

    outcome = await _draw(pool).call(
        {
            "symbol": "US100",
            "add": [
                {"kind": "level", "price": 21500.0, "at": "2026-01-03T09:00:00Z"},
                {"kind": "zone", "top": 21600.0, "bottom": 21550.0},
                {
                    "kind": "trendline",
                    "a": {"time": "2026-01-03T09:00:00Z", "price": 21000.0},
                    "b": {"time": "2026-01-04T09:00:00Z", "price": 21400.0},
                },
            ],
        },
        session_id=session.id,
    )

    assert outcome.kind is ToolOutcomeKind.OK
    kinds = [type(d.geometry) for d in await store.list_drawings(db, symbol="US100")]
    assert kinds == [ChartLevel, ChartZone, ChartTrendline]


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


# --- what it refuses -----------------------------------------------------------------


async def test_a_symbol_the_archive_does_not_collect_is_refused_with_the_ones_it_does(
    db, pool
) -> None:
    session = await _session(db)

    outcome = await _draw(pool).call(
        {"symbol": "EURUSD", "add": [A_LEVEL]}, session_id=session.id
    )

    assert outcome.kind is ToolOutcomeKind.REFUSED
    assert "GOLD" in outcome.text and "US100" in outcome.text
    assert await store.list_drawings(db, symbol="EURUSD") == []


async def test_a_colour_the_chart_cannot_draw_is_refused_and_nothing_lands(db, pool) -> None:
    """Three drawings, one bad colour, none written (specs/agent-chart-drawings,
    "Wywołanie z jednym rysunkiem nie do przyjęcia")."""
    session = await _session(db)

    outcome = await _draw(pool).call(
        {
            "symbol": "US100",
            "add": [
                {"kind": "level", "price": 21500.0},
                {"kind": "level", "price": 21400.0, "color": "hotpink"},
                {"kind": "level", "price": 21300.0},
            ],
        },
        session_id=session.id,
    )

    assert outcome.kind is ToolOutcomeKind.REFUSED
    assert "hotpink" in outcome.text
    assert await store.list_drawings(db, symbol="US100") == []


async def test_a_zone_with_inverted_prices_names_both(db, pool) -> None:
    session = await _session(db)

    outcome = await _draw(pool).call(
        {"symbol": "US100", "add": [{"kind": "zone", "top": 21400.0, "bottom": 21600.0}]},
        session_id=session.id,
    )

    assert outcome.kind is ToolOutcomeKind.REFUSED
    assert "21400" in outcome.text and "21600" in outcome.text
    assert await store.list_drawings(db, symbol="US100") == []


async def test_a_zone_with_equal_prices_is_not_a_zone(db, pool) -> None:
    session = await _session(db)

    outcome = await _draw(pool).call(
        {"symbol": "US100", "add": [{"kind": "zone", "top": 21500.0, "bottom": 21500.0}]},
        session_id=session.id,
    )

    assert outcome.kind is ToolOutcomeKind.REFUSED
    assert await store.list_drawings(db, symbol="US100") == []


async def test_a_zone_that_ends_before_it_starts_is_refused(db, pool) -> None:
    """Not a `CHECK`, unlike every other shape rule: a zone's two moments are both
    optional, so the database has nothing to pin their order against. The terminal draws
    such a band as a rectangle of zero width — a drawing that silently is not there."""
    session = await _session(db)

    outcome = await _draw(pool).call(
        {
            "symbol": "US100",
            "add": [
                {
                    "kind": "zone",
                    "top": 21600.0,
                    "bottom": 21550.0,
                    "from": "2026-01-05T09:00:00Z",
                    "to": "2026-01-03T09:00:00Z",
                }
            ],
        },
        session_id=session.id,
    )

    assert outcome.kind is ToolOutcomeKind.REFUSED
    assert "ends before it starts" in outcome.text
    assert await store.list_drawings(db, symbol="US100") == []


async def test_a_zone_open_ended_in_time_is_accepted(db, pool) -> None:
    session = await _session(db)

    outcome = await _draw(pool).call(
        {
            "symbol": "US100",
            "add": [
                {
                    "kind": "zone",
                    "top": 21600.0,
                    "bottom": 21550.0,
                    "from": "2026-01-03T09:00:00Z",
                }
            ],
        },
        session_id=session.id,
    )

    assert outcome.kind is ToolOutcomeKind.OK
    [standing] = await store.list_drawings(db, symbol="US100")
    assert isinstance(standing.geometry, ChartZone)
    assert standing.geometry.to is None


async def test_an_id_no_column_could_hold_is_refused_rather_than_raised(db, pool) -> None:
    """A model inventing a long number must get a sentence back, not a dead turn: asyncpg
    refuses an integer past `bigint` by raising, and Python's ints have no such ceiling."""
    session = await _session(db)

    outcome = await _draw(pool).call(
        {"symbol": "US100", "remove": [10**25]}, session_id=session.id
    )

    assert outcome.kind is ToolOutcomeKind.REFUSED
    assert "no drawing" in outcome.text


async def test_a_trendline_with_both_points_at_one_moment_is_refused(db, pool) -> None:
    session = await _session(db)

    outcome = await _draw(pool).call(
        {
            "symbol": "US100",
            "add": [
                {
                    "kind": "trendline",
                    "a": {"time": "2026-01-03T09:00:00Z", "price": 21000.0},
                    "b": {"time": "2026-01-03T09:00:00Z", "price": 21400.0},
                }
            ],
        },
        session_id=session.id,
    )

    assert outcome.kind is ToolOutcomeKind.REFUSED
    assert "apart in time" in outcome.text
    assert await store.list_drawings(db, symbol="US100") == []


async def test_a_price_at_or_below_zero_is_refused(db, pool) -> None:
    session = await _session(db)

    outcome = await _draw(pool).call(
        {"symbol": "US100", "add": [{"kind": "level", "price": 0}]},
        session_id=session.id,
    )

    assert outcome.kind is ToolOutcomeKind.REFUSED
    assert "above zero" in outcome.text
    assert await store.list_drawings(db, symbol="US100") == []


async def test_the_ceiling_refuses_the_whole_call(db, pool) -> None:
    session = await _session(db)
    await store.add_drawings(
        db,
        session_id=session.id,
        symbol="US100",
        geometries=[
            ChartLevel(price=float(20000 + n)) for n in range(MAX_DRAWINGS_PER_SYMBOL - 1)
        ],
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


async def test_a_call_that_neither_adds_nor_removes_is_refused(db, pool) -> None:
    session = await _session(db)

    outcome = await _draw(pool).call({"symbol": "US100"}, session_id=session.id)

    assert outcome.kind is ToolOutcomeKind.REFUSED
    assert "nothing to do" in outcome.text


async def test_without_a_tool_server_it_refuses_rather_than_drawing_blind(db, pool) -> None:
    session = await _session(db)

    outcome = await DrawOnChartTool(pool, None).call(
        {"symbol": "US100", "add": [A_LEVEL]}, session_id=session.id
    )

    assert outcome.kind is ToolOutcomeKind.REFUSED
    assert await store.list_drawings(db, symbol="US100") == []


async def test_an_archive_that_does_not_answer_is_not_a_reason_to_guess(db, pool) -> None:
    session = await _session(db)

    outcome = await _draw(pool, FakeToolServer(failing=True)).call(
        {"symbol": "US100", "add": [A_LEVEL]}, session_id=session.id
    )

    assert outcome.kind is ToolOutcomeKind.REFUSED
    assert await store.list_drawings(db, symbol="US100") == []


# --- what it reads -------------------------------------------------------------------


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


async def test_the_read_is_safe_to_repeat(db, pool) -> None:
    session = await _session(db)
    await store.add_drawings(
        db, session_id=session.id, symbol="US100", geometries=[ChartLevel(price=21500.0)]
    )

    first = await _read(pool).call({"symbol": "US100"})
    second = await _read(pool).call({"symbol": "US100"})

    assert first.text == second.text


async def test_the_read_does_not_show_another_instruments_drawings(db, pool) -> None:
    session = await _session(db)
    await store.add_drawings(
        db, session_id=session.id, symbol="GOLD", geometries=[ChartLevel(price=2400.0)]
    )

    outcome = await _read(pool).call({"symbol": "US100"})

    assert json.loads(outcome.text)["drawings"] == []


async def test_the_read_answers_without_an_archive(db, pool) -> None:
    """`list_chart_drawings` never asks market-mcp anything — it reads this module's own
    table, and the prompt promises the operator exactly that."""
    session = await _session(db)
    await store.add_drawings(
        db, session_id=session.id, symbol="US100", geometries=[ChartLevel(price=21500.0)]
    )

    outcome = await _read(pool).call({"symbol": "US100"})

    assert outcome.kind is ToolOutcomeKind.OK
    assert len(json.loads(outcome.text)["drawings"]) == 1


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
    outcome = await _draw(pool).call(
        {"symbol": "US100", "remove": [first_id]}, session_id=session.id
    )

    assert outcome.kind is ToolOutcomeKind.OK
    remaining = await store.list_drawings(db, symbol="US100")
    assert [d.id for d in remaining] == [read["drawings"][1]["id"]]


# --- the palette a drawing is drawn from ---------------------------------------------


async def test_a_colour_from_the_drawing_palette_is_taken(db, pool) -> None:
    """specs/agent-chart-drawings, "Kolor z palety rysunków"."""
    session = await _session(db)

    outcome = await _draw(pool).call(
        {"symbol": "US100", "add": [{"kind": "level", "price": 21500.0, "color": "--color-drawing-2"}]},
        session_id=session.id,
    )

    assert outcome.kind is ToolOutcomeKind.OK
    standing = await store.list_drawings(db, symbol="US100")
    assert [drawing.geometry.color for drawing in standing] == ["--color-drawing-2"]


async def test_an_indicator_colour_is_refused_and_named(db, pool) -> None:
    """A drawing is not an indicator, and wearing its colour is exactly what made the two
    indistinguishable on one chart. The refusal names the token so the model can correct
    it in the same turn (specs/agent-chart-drawings, "Kolor spoza palety rysunków")."""
    session = await _session(db)

    outcome = await _draw(pool).call(
        {"symbol": "US100", "add": [{"kind": "level", "price": 21500.0, "color": "--color-accent"}]},
        session_id=session.id,
    )

    assert outcome.kind is ToolOutcomeKind.REFUSED
    assert "--color-accent" in outcome.text
    assert "--color-drawing-1" in outcome.text
    assert await store.list_drawings(db, symbol="US100") == []


def test_the_tool_offers_the_drawing_palette_and_no_indicator_token() -> None:
    """What the model sees before it picks: a schema offering a colour that can only be
    refused is a schema that lies."""
    from agent.tools.chart import CHART_COLORS, DRAWING_COLORS
    from agent.tools.drawings import DRAW_TOOL

    offered = set()
    for shape in DRAW_TOOL.input_schema["properties"]["add"]["items"]["oneOf"]:
        offered.update(shape["properties"]["color"]["enum"])

    assert offered == set(DRAWING_COLORS)
    assert offered.isdisjoint(CHART_COLORS)


# --- hiding, which is not removing ---------------------------------------------------


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
    # Everything else is exactly what it was — that is the whole difference from removing.
    assert after.id == standing.id
    assert after.created_at == standing.created_at
    assert after.geometry == standing.geometry


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


async def test_hiding_and_showing_one_id_at_once_is_refused(db, pool) -> None:
    """Two opposite orders about one drawing have no outcome the model could have
    predicted (specs/agent-chart-drawings, "Zgaszenie i zapalenie jednego rysunku naraz")."""
    session = await _session(db)
    [standing] = await store.add_drawings(
        db, session_id=session.id, symbol="US100", geometries=[ChartLevel(price=21500.0)]
    )

    outcome = await _draw(pool).call(
        {"symbol": "US100", "hide": [standing.id], "show": [standing.id]}, session_id=session.id
    )

    assert outcome.kind is ToolOutcomeKind.REFUSED
    assert str(standing.id) in outcome.text
    assert (await store.list_drawings(db, symbol="US100"))[0].hidden is False


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


async def test_an_id_from_another_instrument_is_not_hideable(db, pool) -> None:
    session = await _session(db)
    [elsewhere] = await store.add_drawings(
        db, session_id=session.id, symbol="GOLD", geometries=[ChartLevel(price=2400.0)]
    )

    outcome = await _draw(pool).call(
        {"symbol": "US100", "hide": [elsewhere.id]}, session_id=session.id
    )

    assert outcome.kind is ToolOutcomeKind.REFUSED
    assert (await store.list_drawings(db, symbol="GOLD"))[0].hidden is False


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
    """"Hide the old resistance and put up the new one" is one move, not two — the reason
    hiding went into this tool rather than beside it (design.md, "`hide`/`show`
    w `draw_on_chart`, nie czwarte narzędzie do wykresu")."""
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


async def test_the_confirmation_says_hidden_rather_than_removed(db, pool) -> None:
    # The operator reads this back through the model, and one of the two is undoable.
    session = await _session(db)
    [standing] = await store.add_drawings(
        db, session_id=session.id, symbol="US100", geometries=[ChartLevel(price=21500.0)]
    )

    outcome = await _draw(pool).call({"symbol": "US100", "hide": [standing.id]}, session_id=session.id)

    assert "hid" in outcome.text
    assert "removed" not in outcome.text


async def test_a_call_that_only_names_empty_lists_is_still_refused(db, pool) -> None:
    session = await _session(db)

    outcome = await _draw(pool).call(
        {"symbol": "US100", "add": [], "remove": [], "hide": [], "show": []},
        session_id=session.id,
    )

    assert outcome.kind is ToolOutcomeKind.REFUSED


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

    payload = json.loads(outcome.text)
    assert [d["hidden"] for d in payload["drawings"]] == [True, False]


def test_the_tool_offers_hide_and_show_beside_remove() -> None:
    from agent.tools.drawings import DRAW_TOOL

    properties = DRAW_TOOL.input_schema["properties"]
    assert {"add", "remove", "hide", "show"} <= properties.keys()
    # The one distinction the model has to carry away from this schema.
    assert "without deleting" in properties["hide"]["description"]
