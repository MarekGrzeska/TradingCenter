"""The delay's two bounds and a source's figures — the rule lives here, so the routes and the screens are
tested only for carrying it."""

from __future__ import annotations

from datetime import timedelta

import pytest

from social_data.news import latency
from social_data.news.models import Unmeasured

from .builders import NOON

MINUTE = timedelta(minutes=1)


def measured(published, previous, seen):
    return latency.delay(published_at=published, first_seen_at=seen, previous_fetch_at=previous)


def test_a_feed_that_was_late_has_a_lower_bound_above_zero():
    delay = measured(NOON, NOON + 3 * MINUTE, NOON + 5 * MINUTE)

    assert (delay.lower_seconds, delay.upper_seconds, delay.unmeasured) == (180, 300, None)


def test_a_feed_that_published_between_our_two_fetches_has_a_lower_bound_of_zero():
    delay = measured(NOON + 4 * MINUTE, NOON + 3 * MINUTE, NOON + 5 * MINUTE)

    assert (delay.lower_seconds, delay.upper_seconds) == (0, 60)


@pytest.mark.parametrize(
    ("published", "previous", "reason"),
    [
        (None, NOON, Unmeasured.NO_PUBLISH_TIME),
        (NOON, None, Unmeasured.FOUND_THERE),
        (NOON + 60 * MINUTE, NOON, Unmeasured.PUBLISH_TIME_IN_FUTURE),
    ],
)
def test_what_cannot_be_measured_says_why_and_is_never_zero(published, previous, reason):
    delay = measured(published, previous, NOON + 5 * MINUTE if published is None else NOON)

    assert (delay.lower_seconds, delay.upper_seconds, delay.unmeasured) == (None, None, reason)


def test_a_publish_time_a_clock_tolerance_ahead_is_still_measured():
    delay = measured(NOON + MINUTE, NOON - MINUTE, NOON)

    assert delay.unmeasured is None
    assert delay.upper_seconds == 0


@pytest.mark.parametrize("previous_minutes", [0, 1, 2, 4, 5])
@pytest.mark.parametrize("published_minutes", [-3, 0, 1, 4])
def test_the_two_bounds_differ_by_no_more_than_the_gap_between_our_two_fetches(
    previous_minutes, published_minutes
):
    """What separates them is this archive's own polling, so it can never exceed the time between fetches."""
    seen = NOON + 5 * MINUTE
    previous = NOON + previous_minutes * MINUTE
    delay = measured(NOON + published_minutes * MINUTE, previous, seen)

    if delay.unmeasured is None:
        assert delay.upper_seconds - delay.lower_seconds <= (seen - previous).total_seconds()
        assert delay.lower_seconds <= delay.upper_seconds
