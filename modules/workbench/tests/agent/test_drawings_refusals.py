"""What `draw_on_chart` refuses before it reaches for anything. The whole argument object is parsed first,
so every refusal below happens with no database and no tool server involved — a permutation that needed a
PostgreSQL container to prove "21400 is not above 21600" was paying container time for arithmetic.

The behaviour that does reach the database is `test_drawings_tool.py`'s."""

from __future__ import annotations

import pytest

from agent.tools import ToolOutcomeKind
from agent.tools.drawings import DRAW_TOOL, DrawOnChartTool

A_ZONE = {"kind": "zone", "top": 21600.0, "bottom": 21550.0}


def _tool() -> DrawOnChartTool:
    """No pool and no tool server: reaching either one would be the bug this file guards."""
    return DrawOnChartTool(None, None)  # pyright: ignore[reportArgumentType]


@pytest.mark.parametrize(
    ("arguments", "expected_fragments"),
    [
        pytest.param(
            {"symbol": "US100", "add": [{"kind": "zone", "top": 21400.0, "bottom": 21600.0}]},
            ["21400", "21600"],
            id="a zone with inverted prices names both",
        ),
        pytest.param(
            {"symbol": "US100", "add": [{"kind": "zone", "top": 21500.0, "bottom": 21500.0}]},
            [],
            id="a zone with equal prices is not a zone",
        ),
        pytest.param(
            {
                "symbol": "US100",
                "add": [
                    {**A_ZONE, "from": "2026-01-05T09:00:00Z", "to": "2026-01-03T09:00:00Z"}
                ],
            },
            ["ends before it starts"],
            # Not a `CHECK`, unlike every other shape rule: a zone's two moments are both optional, so the
            # database has nothing to pin their order against.
            id="a zone that ends before it starts",
        ),
        pytest.param(
            {"symbol": "US100", "add": [{"kind": "level", "price": 0}]},
            ["above zero"],
            id="a price at or below zero",
        ),
        pytest.param(
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
            ["apart in time"],
            id="a trendline with both points at one moment",
        ),
        pytest.param(
            {"symbol": "US100", "add": [{"kind": "level", "price": 21500.0, "color": "hotpink"}]},
            ["hotpink"],
            id="a colour the chart cannot draw",
        ),
        pytest.param(
            {
                "symbol": "US100",
                "add": [{"kind": "level", "price": 21500.0, "color": "--color-accent"}],
            },
            ["--color-accent", "--color-drawing-1"],
            # A drawing is not an indicator, and wearing its colour is what made the two indistinguishable
            # on one chart. The refusal names the palette so the model can correct it in the same turn.
            id="an indicator colour is named along with the palette",
        ),
        pytest.param(
            {"symbol": "US100", "remove": [10**25]},
            ["no drawing"],
            # asyncpg refuses an integer past `bigint` by raising, and Python's ints have
            # no such ceiling — a raised exception is a dead turn where this is a sentence.
            id="an id no column could hold is refused rather than raised",
        ),
        pytest.param(
            {"symbol": "US100"},
            ["nothing to do"],
            id="a call that neither adds nor removes",
        ),
        pytest.param(
            {"symbol": "US100", "add": [], "remove": [], "hide": [], "show": []},
            ["nothing to do"],
            id="a call that only names empty lists",
        ),
        pytest.param(
            {"symbol": "US100", "hide": [7], "show": [7]},
            ["#7", "`hide`", "`show`"],
            # Two opposite orders about one drawing have no outcome the model could have predicted.
            id="hiding and showing one id at once",
        ),
        pytest.param(
            {"symbol": "US100", "remove": [7], "hide": [7]},
            ["#7", "`remove`", "`hide`"],
            # Without this the removal runs first and the hiding refuses as "no drawing with that id",
            # sending the model after a wrong id rather than at its own two lists.
            id="removing and hiding one id at once is refused by name",
        ),
    ],
)
async def test_a_call_that_cannot_be_carried_out_is_refused_in_a_sentence(
    arguments: dict, expected_fragments: list[str]
) -> None:
    outcome = await _tool().call(arguments, session_id=1)

    assert outcome.kind is ToolOutcomeKind.REFUSED
    for fragment in expected_fragments:
        assert fragment in outcome.text


def test_the_tool_offers_the_drawing_palette_and_no_indicator_token() -> None:
    """What the model sees before it picks: a schema offering a colour that can only be
    refused is a schema that lies."""
    from agent.tools.chart import CHART_COLORS, DRAWING_COLORS

    offered = set()
    for shape in DRAW_TOOL.input_schema["properties"]["add"]["items"]["oneOf"]:
        offered.update(shape["properties"]["color"]["enum"])

    assert offered == set(DRAWING_COLORS)
    assert offered.isdisjoint(CHART_COLORS)


def test_the_tool_offers_hide_and_show_beside_remove() -> None:
    properties = DRAW_TOOL.input_schema["properties"]
    assert {"add", "remove", "hide", "show"} <= properties.keys()
    # The one distinction the model has to carry away from this schema.
    assert "without deleting" in properties["hide"]["description"]
