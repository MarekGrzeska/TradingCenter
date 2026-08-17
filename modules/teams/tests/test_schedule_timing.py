"""What a cron expression means in time — `teams/scheduler/timing.py`, and the folding of
missed slots that reads it (`scheduler/clock.py::_next_fire_and_skipped`).

The expression is a wall clock in Poland; everything this module stores and publishes is
UTC. These tests are the record of that pair, including the two nights a year where a wall
clock is not a function.
"""

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
    """29 March 2026 has no 02:30 in Poland — the clocks jump 02:00 → 03:00. The schedule
    MUST NOT be skipped for the day; what `croniter` picks is recorded here rather than
    argued about."""
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
