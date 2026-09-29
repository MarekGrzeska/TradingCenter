"""What a feed document becomes. Parsed from saved documents, because a feed is somebody else's format and the
day it changes shape is a code change here rather than a mystery on a screen."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from social_data.news import feed

FIXTURES = Path(__file__).parent / "fixtures"


def read(name: str, publisher: str = "A Publisher"):
    return feed.items_from((FIXTURES / name).read_bytes(), publisher=publisher)


def test_an_rss_item_becomes_text_with_entities_resolved_and_a_utc_time():
    [talks, *_] = read("news_rss.xml")

    assert talks.title == "US-Iran talks in New York: What’s the latest?"
    assert talks.summary == "Delegations met & adjourned."
    assert talks.external_id == "guid-talks"
    assert talks.published_at == datetime(2026, 9, 29, 15, 9, tzinfo=UTC)


def test_what_has_no_identity_or_no_title_is_dropped_and_a_missing_guid_falls_back_to_the_link():
    ids = [item.external_id for item in read("news_rss.xml")]

    assert ids == ["guid-talks", "https://example.com/dc", "https://example.com/only-link"]


def test_a_time_that_cannot_be_read_is_none_and_never_a_guess():
    by_id = {item.external_id: item for item in read("news_rss.xml")}

    assert by_id["https://example.com/only-link"].published_at is None
    assert by_id["https://example.com/dc"].published_at == datetime(2026, 9, 29, 13, 0, tzinfo=UTC)


def test_an_aggregator_item_is_filed_under_the_publisher_it_names_without_repeating_it_in_the_title():
    [item] = read("news_google.xml", publisher="Google News")

    assert item.publisher == "Reuters"
    assert item.title == "Hormuz shipping resumes after talks"
    assert item.summary == ""


def test_an_atom_entry_reads_the_alternate_link_and_prefers_published_to_updated():
    [item] = read("news_atom.xml")

    assert item.url == "https://example.com/atom-1"
    assert item.published_at == datetime(2026, 9, 29, 15, 30, tzinfo=UTC)
    assert item.summary == "A short lead."


def test_a_long_lead_is_cut():
    long = "<rss><channel><item><title>t</title><guid>g</guid><description>" + "word " * 500
    long += "</description></item></channel></rss>"

    [item] = feed.items_from(long, publisher="P")

    assert len(item.summary) <= feed.SUMMARY_LIMIT


@pytest.mark.parametrize(
    "document", ["<html><body>Just a moment...</body></html>", "not xml at all"]
)
def test_a_document_that_is_not_a_feed_is_unreadable(document):
    with pytest.raises(feed.Unreadable):
        feed.items_from(document, publisher="P")
