"""What a cron expression means in time, and the folding of missed slots that reads it. The expression is a
wall clock in Poland and everything stored is UTC — including the two nights a year where it is not a function."""

from __future__ import annotations

from datetime import UTC, datetime

from teams.scheduler.clock import _next_fire_and_skipped
from teams.scheduler.timing import SCHEDULE_TIMEZONE, fires_after, next_fire_after


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def test_nine_in_the_morning_is_nine_in_poland_in_summer() -> None:
    # 2026-07-01: CEST, UTC+2.
    assert next_fire_after("0 9 * * *", _utc("2026-07-01T05:00:00")) == _utc("2026-07-01T07:00:00")


def test_nine_in_the_morning_is_nine_in_poland_in_winter() -> None:
    # 2026-01-07: CET, UTC+1 — the same expression, an hour later in UTC.
    assert next_fire_after("0 9 * * *", _utc("2026-01-07T05:00:00")) == _utc("2026-01-07T08:00:00")


def test_the_clock_change_moves_utc_and_leaves_the_wall_clock_alone() -> None:
    """Across the last Sunday of October 2026, a daily 9:00 schedule stays at 9:00 in
    Poland while its UTC moment steps back by an hour."""
    fires = fires_after("0 9 * * *", _utc("2026-10-24T00:00:00"))
    moments = [next(fires) for _ in range(4)]

    assert moments == [
        _utc("2026-10-24T07:00:00"),
        _utc("2026-10-25T08:00:00"),  # the clocks went back overnight
        _utc("2026-10-26T08:00:00"),
        _utc("2026-10-27T08:00:00"),
    ]
    assert {moment.astimezone(SCHEDULE_TIMEZONE).hour for moment in moments} == {9}


def test_a_schedule_inside_the_spring_gap_still_fires_that_day() -> None:
    """29 March 2026 has no 02:30 in Poland. The schedule MUST NOT be skipped for the day; what `croniter`
    picks is recorded here rather than argued about."""
    fires = fires_after("30 2 * * *", _utc("2026-03-28T12:00:00"))
    moments = [next(fires) for _ in range(2)]

    days = [moment.astimezone(SCHEDULE_TIMEZONE).date().isoformat() for moment in moments]
    assert days == ["2026-03-29", "2026-03-30"]


def test_missed_slots_fold_into_one_and_are_counted() -> None:
    due_at = _utc("2026-07-01T06:00:00")
    now = _utc("2026-07-01T06:22:00")

    next_fire_at, skipped = _next_fire_and_skipped("*/5 * * * *", due_at, now)

    assert next_fire_at == _utc("2026-07-01T06:25:00")
    assert skipped == 4  # 06:05, 06:10, 06:15, 06:20


def test_folding_rolls_a_daily_schedule_forward_in_polish_time() -> None:
    due_at = _utc("2026-07-01T07:00:00")
    now = _utc("2026-07-03T05:00:00")

    next_fire_at, skipped = _next_fire_and_skipped("0 9 * * *", due_at, now)

    assert next_fire_at == _utc("2026-07-03T07:00:00")
    assert skipped == 1  # 2 July


def test_an_hourly_expression_with_weekdays_steps_over_the_weekend() -> None:
    """The rhythm the operator wanted: every hour at :35, Monday to Friday, with Friday's last fire followed
    by Monday's first. Times are UTC, so 21:35 Polish summer time is 19:35 here."""
    friday_last = next_fire_after("35 * * * 1,2,3,4,5", _utc("2026-08-21T21:00:00"))
    assert friday_last == _utc("2026-08-21T21:35:00")

    after_friday = next_fire_after("35 * * * 1,2,3,4,5", friday_last)
    # 2026-08-24 is the Monday; 00:35 in Poland is 22:35 UTC on the Sunday.
    assert after_friday == _utc("2026-08-23T22:35:00")
    assert after_friday.astimezone(SCHEDULE_TIMEZONE).isoweekday() == 1


def test_a_week_of_an_hourly_weekday_rhythm_never_lands_on_a_weekend() -> None:
    fires = fires_after("35 * * * 1,2,3,4,5", _utc("2026-08-17T00:00:00"))
    days = {next(fires).astimezone(SCHEDULE_TIMEZONE).isoweekday() for _ in range(200)}
    assert days == {1, 2, 3, 4, 5}
