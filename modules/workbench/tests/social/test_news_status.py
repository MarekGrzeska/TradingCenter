"""What a source's status is called, from its own interval: the difference between a feed that is failing, one
that has stopped, and one that is quiet but answering."""

from __future__ import annotations

from datetime import timedelta

from social_data.news import views
from social_data.news.models import SourceRow
from social_data.news.sources import NewsSource

from .builders import NOON

SOURCE = NewsSource("a-feed", "A", "https://example.com/rss", 120)


def row(**kwargs) -> SourceRow:
    fields = {
        "source": "a-feed",
        "last_attempt_at": NOON,
        "last_success_at": NOON,
        "last_failure_at": None,
        "last_failure": None,
        "newest_published_at": None,
    }
    return SourceRow(**{**fields, **kwargs})


def test_a_feed_never_tried_is_pending_and_one_that_never_answered_is_stale():
    assert views.status(SOURCE, None, now=NOON) == "pending"
    assert (
        views.status(SOURCE, row(last_attempt_at=None, last_success_at=None), now=NOON) == "pending"
    )
    assert views.status(SOURCE, row(last_success_at=None), now=NOON) == "stale"


def test_a_feed_answering_within_its_intervals_is_ok_even_if_nothing_new_was_published():
    quiet = row(newest_published_at=NOON - timedelta(hours=6))

    assert views.status(SOURCE, quiet, now=NOON + timedelta(minutes=2)) == "ok"


def test_a_feed_whose_latest_fetch_failed_is_failing_until_it_has_been_silent_for_six_intervals():
    failed = row(last_failure_at=NOON + timedelta(minutes=2), last_failure="refused: HTTP 403")

    assert views.status(SOURCE, failed, now=NOON + timedelta(minutes=3)) == "failing"
    assert views.status(SOURCE, failed, now=NOON + timedelta(minutes=13)) == "stale"


def test_a_feed_that_failed_once_and_then_answered_is_ok_again():
    recovered = row(
        last_failure_at=NOON - timedelta(minutes=5), last_success_at=NOON, last_failure="refused"
    )

    assert views.status(SOURCE, recovered, now=NOON + timedelta(minutes=1)) == "ok"
