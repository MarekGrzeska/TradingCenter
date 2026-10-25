"""A session's clock at its lowest layer: numbered bars and minutes to the close, in the session's own zone
(`strategies-language`, "Sesja liczona zegarem w swojej strefie")."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np

from strategies import sessions
from strategies.vocabulary import SESSIONS

FIVE_MINUTES = 300


def _at(text: str) -> int:
    return int(datetime.fromisoformat(text).replace(tzinfo=UTC).timestamp())


def _numbers(starts: list[int], period: int = FIVE_MINUTES) -> dict[int, float]:
    axis = np.array(starts, dtype=np.int64)
    days = sessions.days(SESSIONS["NEW_YORK"], int(axis[0]), int(axis[-1] + period))
    return dict(zip(starts, days.bar_number(axis, period).tolist(), strict=True))


def _minutes_to_close(closes: list[int]) -> list[float]:
    moments = np.array(closes, dtype=np.int64)
    return sessions.days(SESSIONS["NEW_YORK"], closes[0], closes[-1]).minutes_to_close(moments).tolist()


def test_the_first_m5_bar_of_new_york_is_one_and_the_next_two() -> None:
    before, first, second = _at("2026-07-02T13:25"), _at("2026-07-02T13:30"), _at("2026-07-02T13:35")

    assert _numbers([before, first, second]) == {before: 0, first: 1, second: 2}


def test_new_york_opens_an_hour_earlier_in_poland_while_europe_has_changed_time_and_the_us_has_not() -> None:
    late_october = [_at("2026-10-27T13:25"), _at("2026-10-27T13:30")]
    december = [_at("2026-12-01T13:30"), _at("2026-12-01T14:30")]

    assert list(_numbers(late_october).values()) == [0, 1]
    assert list(_numbers(december).values()) == [0, 1]


def test_a_missing_opening_bar_does_not_renumber_the_day() -> None:
    day = [_at("2026-07-02T13:25"), *range(_at("2026-07-02T13:35"), _at("2026-07-02T14:00"), FIVE_MINUTES)]

    numbers = _numbers(day)

    assert numbers[_at("2026-07-02T13:35")] == 2 and 1 not in numbers.values()


def test_an_hour_bar_holding_the_open_is_outside_and_the_next_one_is_the_first() -> None:
    assert list(_numbers([_at("2026-07-02T13:00"), _at("2026-07-02T14:00")], period=3600).values()) == [0, 1]


def test_minutes_to_the_close_are_counted_from_the_decision_and_turn_negative_after_it() -> None:
    assert _minutes_to_close([_at("2026-07-02T19:55"), _at("2026-07-02T20:10")]) == [5, -10]


def test_a_saturday_has_no_session() -> None:
    saturday = _at("2026-07-04T14:00")

    assert _numbers([saturday]) == {saturday: 0}
    assert np.isnan(_minutes_to_close([saturday])[0])
