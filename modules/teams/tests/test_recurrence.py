"""The rhythm ↔ cron pair, both ways — `teams/recurrence.py`.

No database and no clock: this is a translation, and the one property worth holding it to
is that the two directions agree.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from teams.recurrence import Recurrence, from_cron, to_cron

RHYTHMS = [
    (Recurrence(kind="every_minutes", minutes=5), "*/5 * * * *"),
    (Recurrence(kind="hourly", minute=0), "0 * * * *"),
    (Recurrence(kind="hourly", minute=30), "30 * * * *"),
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
