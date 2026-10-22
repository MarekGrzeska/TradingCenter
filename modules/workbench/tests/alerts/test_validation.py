"""What a rule is refused for. One case per reason: the rule of how much test is enough — a domain rule once, at the
lowest layer that holds it — and the REST file asks only that the reasons reach the wire."""

from __future__ import annotations

import pytest

from alerts.contract import FilterTerm
from alerts.validation import validate

from .builders import FILM_SCHEMA, condition, event, known, rule, tool

QUIET = FilterTerm(attribute="channel", op="eq", value="Some channel")


def fields_of(candidate, **kwargs) -> set[str]:
    return {defect.field for defect in validate(candidate, known(**kwargs))}


def test_a_rule_that_can_work_has_no_defects() -> None:
    assert validate(rule(), known()) == []
    assert validate(rule(event([QUIET])), known()) == []


@pytest.mark.parametrize(
    ("source", "field"),
    [
        (condition(tool_name="get_candles_of_nothing"), "source.tool_name"),
        (condition(tool_name="add_channel"), "source.tool_name"),
        (condition(arguments={"symbol": "EURUSD", "limit": 3}), "source.arguments.limit"),
        (condition(arguments={"symbol": 7}), "source.arguments.symbol"),
        (condition(arguments={}), "source.arguments"),
        (condition(field_path="symbol"), "source.field_path"),
        (condition(field_path="close.missing"), "source.field_path"),
        (condition(poll_interval_seconds=5), "source.poll_interval_seconds"),
    ],
)
def test_a_value_rule_is_refused_for_each_reason_it_could_not_work(source, field) -> None:
    assert field in fields_of(rule(source))


@pytest.mark.parametrize(
    ("source", "field"),
    [
        (event(event_type="nobody.announced.this"), "source.event_type"),
        (event([FilterTerm(attribute="channle", op="eq", value="x")]), "source.filter.0.attribute"),
        (event([FilterTerm(attribute="channel", op="gt", value="x")]), "source.filter.0.op"),
        (event([FilterTerm(attribute="impact_score", op="gte", value="high")]), "source.filter.0.value"),
        (event([FilterTerm(attribute="channel", op="in", value="x")]), "source.filter.0.value"),
        (event([FilterTerm(attribute="instruments", op="contains", value=3)]), "source.filter.0.value"),
        (event([FilterTerm(attribute="forming", op="eq", value="yes")]), "source.filter.0.value"),
    ],
)
def test_an_event_rule_is_refused_for_each_reason_it_could_not_match(source, field) -> None:
    assert field in fields_of(rule(source))


def test_every_reason_is_named_at_once() -> None:
    bad = rule(condition(tool_name="add_channel"), destination="nobody", template="{nonsense}")

    assert fields_of(bad) == {"source.tool_name", "destination", "template"}


def test_a_recipient_the_door_does_not_know_is_refused_and_no_door_means_no_check() -> None:
    assert "destination" in fields_of(rule(destination="nobody"))
    assert validate(rule(destination="nobody"), known(destinations=None)) == []


def test_a_tool_that_publishes_no_answer_schema_is_let_through() -> None:
    schemaless = tool(output_schema={})

    assert validate(rule(condition(field_path="anything.at.all")), known(tools=[schemaless])) == []


@pytest.mark.parametrize(
    ("template", "refused"),
    [("{rule}: {value} {symbol}", False), ("{values}", True), ("{symbol.__class__}", True), ("{}", True)],
)
def test_a_template_may_fill_only_what_the_rule_has(template: str, refused: bool) -> None:
    assert ("template" in fields_of(rule(template=template))) is refused


def test_an_event_template_may_fill_the_attributes_of_its_type() -> None:
    assert "template" not in fields_of(rule(event(), template="{channel}: {impact_score} — {text}"))
    assert set(FILM_SCHEMA["properties"]) >= {"channel", "impact_score"}


def test_an_interval_below_the_floor_names_the_floor() -> None:
    [defect] = [
        d for d in validate(rule(condition(poll_interval_seconds=5)), known(min_interval_seconds=45)) if d.field.endswith("poll_interval_seconds")
    ]

    assert "45 s" in defect.message


MANY = {"phone": ("postsbot", "filmsbot")}


def test_a_recipient_with_several_bots_needs_the_rule_to_choose_one() -> None:
    assert "bot" in fields_of(rule(), destinations=MANY)
    assert fields_of(rule(bot="filmsbot"), destinations=MANY) == set()


def test_a_bot_the_recipient_is_not_reached_through_is_refused_at_the_bot_field() -> None:
    assert fields_of(rule(bot="otherbot"), destinations=MANY) == {"bot"}
    assert fields_of(rule(bot="@filmsbot"), destinations=MANY) == set()


def test_a_recipient_with_no_bot_yet_is_refused_at_the_recipient() -> None:
    assert fields_of(rule(), destinations={"phone": ()}) == {"destination"}


def test_a_rule_written_without_a_bot_still_works_for_a_recipient_with_one() -> None:
    assert fields_of(rule(), destinations={"phone": ("postsbot",)}) == set()
