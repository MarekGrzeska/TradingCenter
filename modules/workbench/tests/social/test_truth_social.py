"""The parser, against a saved document. The feed is somebody's side project, so what this holds is
the shape it had when the module was written — the day that changes, this is what says so."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest

from social_data.providers import SourceUnreachable, SourceUnreadable
from social_data.providers.truth_social import (
    SOURCE,
    TruthSocialFeed,
    clean,
    posts_from,
    published_at,
)

FEED = (Path(__file__).parent / "fixtures" / "truth_social_feed.xml").read_text(encoding="utf-8")


def test_a_readable_item_becomes_a_post():
    [first, second] = posts_from(FEED)

    assert first.source == SOURCE
    assert first.external_id == "1001"
    assert first.author == "realDonaldTrump"
    assert first.url == "https://trumpstruth.org/statuses/1001"
    assert first.published_at == datetime(2026, 8, 30, 23, 50, tzinfo=UTC)
    assert second.external_id == "1002"


def test_the_text_arrives_without_tags_and_with_entities_resolved():
    [first, _] = posts_from(FEED)

    assert first.content == (
        "TARIFFS on China & Mexico take effect MONDAY. Our Country will be RICH again!"
    )


def test_a_passed_on_post_is_marked_as_one():
    [first, second] = posts_from(FEED)

    assert (first.is_repost, second.is_repost) == (False, True)


def test_an_item_without_an_identifier_or_a_readable_date_is_dropped():
    assert [post.external_id for post in posts_from(FEED)] == ["1001", "1002"]


def test_a_document_that_is_not_a_feed_is_unreadable_not_empty():
    with pytest.raises(SourceUnreadable):
        posts_from("<rss><channel><item>")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Sat, 30 Aug 2026 23:50:00 +0000", datetime(2026, 8, 30, 23, 50, tzinfo=UTC)),
        # A different offset is the same instant, which is what deduplication and windows compare.
        ("Sat, 30 Aug 2026 19:50:00 -0400", datetime(2026, 8, 30, 23, 50, tzinfo=UTC)),
        ("", None),
        ("yesterday", None),
    ],
)
def test_dates_are_read_as_instants_in_utc(raw, expected):
    assert published_at(raw) == expected


def test_cleaning_removes_tags_before_resolving_entities():
    # An entity-encoded tag must survive as text: unescaping first would turn it into a tag that
    # the stripping pass has already run past.
    assert clean("<p>a &lt;b&gt; c</p>") == "a <b> c"


async def test_a_feed_that_does_not_answer_is_unreachable():
    def refuse(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="down")

    async with httpx.AsyncClient(transport=httpx.MockTransport(refuse)) as client:
        feed = TruthSocialFeed(client, feed_url="https://feed.test/feed")
        with pytest.raises(SourceUnreachable):
            await feed.fetch(date(2026, 8, 31))


async def test_the_day_asked_for_is_the_day_requested():
    asked: list[dict] = []

    def answer(request: httpx.Request) -> httpx.Response:
        asked.append(dict(request.url.params))
        return httpx.Response(200, text=FEED)

    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as client:
        feed = TruthSocialFeed(client, feed_url="https://feed.test/feed")
        posts = await feed.fetch(date(2026, 8, 31))

    assert asked == [{"start_date": "2026-08-31", "end_date": "2026-08-31"}]
    assert len(posts) == 2
