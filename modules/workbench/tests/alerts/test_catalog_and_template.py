"""The two pure helpers a rule is built on: which fields of a tool's answer are numbers, and how a message is filled in."""

from __future__ import annotations

import pytest

from alerts import template
from alerts.catalog import number_fields

from .builders import LAST_PRICE_OUTPUT


def test_the_numbers_in_an_answer_are_found_through_null_refs_and_lists() -> None:
    schema = {
        "type": "object",
        "$defs": {"Bar": {"type": "object", "properties": {"high": {"type": "number"}, "label": {"type": "string"}}}},
        "properties": {
            "close": {"anyOf": [{"type": "number"}, {"type": "null"}]},
            "name": {"type": "string"},
            "latest": {"$ref": "#/$defs/Bar"},
            "bars": {"type": "array", "items": {"$ref": "#/$defs/Bar"}},
            "count": {"type": "integer"},
            "open": {"type": "boolean"},
        },
    }

    assert number_fields(schema) == ["close", "latest.high", "bars.0.high", "count"]


def test_what_publishes_no_schema_has_no_known_numbers() -> None:
    assert number_fields(None) == []
    assert number_fields({}) == []
    assert number_fields(LAST_PRICE_OUTPUT) == ["close", "age_seconds"]


def test_a_slot_is_filled_and_a_missing_one_is_empty() -> None:
    assert template.render("{rule}: {value} ({symbol})", {"rule": "EUR", "value": 1.1, "symbol": None}) == "EUR: 1.1 ()"


@pytest.mark.parametrize(("value", "text"), [(2.0, "2"), (True, "tak"), (["a", "b"], "a, b")])
def test_values_read_the_way_a_person_would_say_them(value, text) -> None:
    assert template.render("{x}", {"x": value}) == text


def test_a_template_reaches_nothing_but_the_values_it_was_given() -> None:
    assert template.render("a{x.__class__}b", {"x": "secret"}) == "ab"
    assert template.unknown_slots("{x.__class__} {y}", ["x", "y"]) == ["x.__class__"]


def test_a_message_longer_than_the_limit_is_cut_and_says_so() -> None:
    cut = template.render("{x}", {"x": "a" * 50}, limit=20)

    assert len(cut) == 20
    assert cut.endswith(template.CUT)
