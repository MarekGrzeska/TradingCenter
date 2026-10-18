"""The decision of a value rule, with no clock and no database: what a look found, and whether that is news. Every case
here is a sentence in `alerts-conditions`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from alerts import conditions
from alerts.conditions import Look, decide

from .builders import FakeTools

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
MET = Look("met", value=1.12)
UNMET = Look("unmet", value=1.05)


def verdict(seen: Look, *, known: bool | None, fired_ago: int | None = None, cooldown: int = 900):
    last = None if fired_ago is None else NOW - timedelta(seconds=fired_ago)
    return decide(seen, known=known, last_fired_at=last, cooldown_seconds=cooldown, now=NOW)


def test_the_step_from_no_to_yes_fires() -> None:
    assert verdict(MET, known=False).fire is True


def test_a_yes_that_stays_yes_fires_once_not_every_look() -> None:
    assert verdict(MET, known=True).fire is False


def test_a_no_never_fires() -> None:
    assert verdict(UNMET, known=True).fire is False
    assert verdict(UNMET, known=False).fire is False


def test_the_first_look_sets_the_baseline_even_when_the_value_is_already_over() -> None:
    first = verdict(MET, known=None)

    assert (first.fire, first.baseline) == (False, True)


def test_a_crossing_inside_the_cooldown_is_cooled_not_fired() -> None:
    cooled = verdict(MET, known=False, fired_ago=60)

    assert (cooled.fire, cooled.cooled) == (False, True)
    assert verdict(MET, known=False, fired_ago=901).fire is True


def test_a_look_that_learned_nothing_is_not_a_no_and_not_news() -> None:
    silent = Look("unavailable", reason="down")

    assert silent.result is None
    assert verdict(silent, known=True).fire is False
    assert verdict(silent, known=False).fire is False


async def look_at(tools: FakeTools, **overrides) -> Look:
    values = {
        "tool_name": "get_last_price",
        "arguments": {"symbol": "EURUSD"},
        "field_path": "close",
        "comparison": "gt",
        "threshold": 1.10,
    }
    return await conditions.look(tools, **{**values, **overrides})


async def test_a_price_over_the_level_is_met_and_under_it_is_not() -> None:
    tools = FakeTools()
    tools.price = 1.12
    assert (await look_at(tools)).outcome == "met"
    tools.price = 1.05
    assert (await look_at(tools)).outcome == "unmet"


@pytest.mark.parametrize(
    ("setup", "outcome"),
    [
        (lambda tools: setattr(tools, "price", None), "unavailable"),
        (lambda tools: setattr(tools, "down", True), "unavailable"),
        (lambda tools: setattr(tools, "refuses", True), "refused"),
    ],
)
async def test_what_cannot_be_read_is_told_apart_by_why(setup, outcome) -> None:
    tools = FakeTools()
    setup(tools)

    assert (await look_at(tools)).outcome == outcome


async def test_no_tool_surface_at_all_is_unavailable_not_a_no() -> None:
    assert (await conditions.look(None, tool_name="x", arguments={}, field_path="a", comparison="gt", threshold=1)).outcome == "unavailable"


def test_a_path_goes_through_objects_and_lists_and_stops_at_what_is_not_there() -> None:
    payload = {"bars": [{"high": 3}], "name": "x"}

    assert conditions.walk(payload, "bars.0.high") == 3
    assert conditions.walk(payload, "bars.1.high") is None
    assert conditions.walk(payload, "name.deeper") is None
