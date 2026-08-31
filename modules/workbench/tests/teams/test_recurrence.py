"""The rhythm ↔ cron pair, both ways. No database and no clock: this is a translation, and the one property
worth holding it to is that the two directions agree."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from teams.recurrence import Recurrence, from_cron, to_cron

RHYTHMS = [
    (Recurrence(kind="every_minutes", minutes=5), "*/5 * * * *"),
    (Recurrence(kind="hourly", minute=0), "0 * * * *"),
    (Recurrence(kind="hourly", minute=30), "30 * * * *"),
    # The same two rhythms with the market's own week under them.
    (
        Recurrence(kind="hourly", minute=35, weekdays=[1, 2, 3, 4, 5]),
        "35 * * * 1,2,3,4,5",
    ),
    (
        Recurrence(kind="every_minutes", minutes=15, weekdays=[1, 2, 3, 4, 5]),
        "*/15 * * * 1,2,3,4,5",
    ),
    (Recurrence(kind="hourly", minute=0, weekdays=[6, 7]), "0 * * * 0,6"),
    (Recurrence(kind="daily", hour=9, minute=0), "0 9 * * *"),
    (Recurrence(kind="weekly", hour=9, minute=15, weekdays=[1]), "15 9 * * 1"),
    (Recurrence(kind="weekly", hour=8, minute=0, weekdays=[1, 2, 3, 4, 5]), "0 8 * * 1,2,3,4,5"),
    # ISO Sunday is 7; cron's own Sunday is 0, and 0 is what the canonical form carries.
    (Recurrence(kind="weekly", hour=20, minute=0, weekdays=[6, 7]), "0 20 * * 0,6"),
    (Recurrence(kind="monthly", hour=7, minute=45, day_of_month=1), "45 7 1 * *"),
]


@pytest.mark.parametrize(("recurrence", "expression"), RHYTHMS)
def test_a_rhythm_becomes_its_expression(recurrence: Recurrence, expression: str) -> None:
    assert to_cron(recurrence) == expression


@pytest.mark.parametrize(("recurrence", "expression"), RHYTHMS)
def test_an_expression_becomes_its_rhythm(recurrence: Recurrence, expression: str) -> None:
    assert from_cron(expression) == recurrence


@pytest.mark.parametrize(
    "expression",
    [
        "0 9 * * 1-5",  # a range, not the list the writer produces
        "0 9,17 * * *",  # two hours in one expression
        "0 9 1 1 *",  # a month, which no rhythm has
        "*/5 9 * * *",  # a step outside the plain "every N minutes"
        "0 9 * * 1,0",  # the days the writer would have sorted the other way
        "0 9 1 * 1",  # a day of the month and a weekday at once
        "35 * * * 1-5",  # the range an operator writes by hand, not the list this produces
        "35 * * * 0,1,2,3,4,5,6",  # every day spelled out, which normalises to no day
        "not a cron expression",
    ],
)
def test_an_expression_outside_the_rhythms_is_no_rhythm(expression: str) -> None:
    assert from_cron(expression) is None


def test_a_rhythm_must_carry_what_its_kind_needs() -> None:
    with pytest.raises(ValidationError):
        Recurrence(kind="daily", hour=9)


def test_a_rhythm_must_not_carry_what_its_kind_does_not_use() -> None:
    with pytest.raises(ValidationError):
        Recurrence(kind="daily", hour=9, minute=0, day_of_month=3)


@pytest.mark.parametrize("weekdays", [[], [0], [8], [1, 1]])
def test_weekdays_are_iso_days_named_once(weekdays: list[int]) -> None:
    with pytest.raises(ValidationError):
        Recurrence(kind="weekly", hour=9, minute=0, weekdays=weekdays)


@pytest.mark.parametrize("kind", ["every_minutes", "hourly"])
def test_no_weekdays_is_every_day_and_stays_absent(kind: str) -> None:
    """The shape every schedule saved before this existed has: nothing in the fifth field,
    and a rhythm that reads back without weekdays rather than with all seven."""
    fields = {"minutes": 15} if kind == "every_minutes" else {"minute": 35}
    rhythm = Recurrence(kind=kind, **fields)
    assert rhythm.weekdays is None
    assert to_cron(rhythm).endswith(" *")
    assert from_cron(to_cron(rhythm)) == rhythm


@pytest.mark.parametrize("kind", ["every_minutes", "hourly"])
def test_every_day_named_is_the_same_as_none_named(kind: str) -> None:
    """Two spellings of one trigger would leave `from_cron` answering with one of them and
    the operator reading a rhythm they did not set."""
    fields = {"minutes": 15} if kind == "every_minutes" else {"minute": 35}
    rhythm = Recurrence(kind=kind, weekdays=[1, 2, 3, 4, 5, 6, 7], **fields)
    assert rhythm.weekdays is None
    assert rhythm == Recurrence(kind=kind, **fields)


def test_a_weekly_rhythm_keeps_all_seven_days() -> None:
    """`weekly` is not normalised the same way: seven days at 9:00 is its own expression,
    different from `daily`'s, so it stays a rhythm rather than becoming one."""
    rhythm = Recurrence(kind="weekly", hour=9, minute=0, weekdays=[1, 2, 3, 4, 5, 6, 7])
    assert rhythm.weekdays == [1, 2, 3, 4, 5, 6, 7]
    assert to_cron(rhythm) == "0 9 * * 0,1,2,3,4,5,6"
    assert from_cron("0 9 * * 0,1,2,3,4,5,6") == rhythm


def test_a_daily_rhythm_refuses_weekdays_and_names_the_one_that_takes_them() -> None:
    """Daily plus weekdays is `weekly`'s own expression. Refused rather than accepted, or
    `from_cron` would have two rhythms to answer `0 9 * * 1,2,3,4,5` with."""
    with pytest.raises(ValidationError) as refusal:
        Recurrence(kind="daily", hour=9, minute=0, weekdays=[1, 2, 3, 4, 5])
    assert "weekly" in str(refusal.value)


def test_a_monthly_rhythm_refuses_weekdays_too() -> None:
    with pytest.raises(ValidationError):
        Recurrence(kind="monthly", hour=9, minute=0, day_of_month=1, weekdays=[1])


@pytest.mark.parametrize("kind", ["every_minutes", "hourly"])
def test_naming_no_day_at_all_is_refused_not_read_as_every_day(kind: str) -> None:
    fields = {"minutes": 15} if kind == "every_minutes" else {"minute": 35}
    with pytest.raises(ValidationError):
        Recurrence(kind=kind, weekdays=[], **fields)
