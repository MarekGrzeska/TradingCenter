"""One GET of one feed: what it sends, and which of the five things it answered."""

from __future__ import annotations

import httpx
import pytest

from social_data.news.fetch import Failure, FeedClient, FetchFailed
from social_data.news.sources import NewsSource

from .test_news_feed import FIXTURES

SOURCE = NewsSource("a-feed", "A Publisher", "https://example.com/rss", 120)
FEED = (FIXTURES / "news_rss.xml").read_bytes()


def client_for(handler) -> FeedClient:
    transport = httpx.MockTransport(handler)
    return FeedClient(
        httpx.AsyncClient(transport=transport, headers={"User-Agent": "tradingcenter-test"})
    )


async def test_an_answer_with_items_is_read_and_its_validators_are_sent_next_time():
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        if request.headers.get("If-None-Match") == '"v1"':
            return httpx.Response(304)
        return httpx.Response(200, content=FEED, headers={"ETag": '"v1"'})

    client = client_for(handler)
    first = await client.fetch(SOURCE)
    second = await client.fetch(SOURCE)

    assert len(first.items) == 3 and not first.not_modified
    assert second.not_modified and second.items == []
    assert seen[0].headers["User-Agent"] == "tradingcenter-test"
    assert "If-None-Match" not in seen[0].headers


@pytest.mark.parametrize(
    ("respond", "kind"),
    [
        (lambda request: httpx.Response(403), Failure.REFUSED),
        (lambda request: httpx.Response(429), Failure.REFUSED),
        (lambda request: httpx.Response(504), Failure.UNREACHABLE),
        (
            lambda request: httpx.Response(200, content=b"<html>Just a moment...</html>"),
            Failure.UNREADABLE,
        ),
        (lambda request: httpx.Response(200, content=b"x" * (6 * 1024 * 1024)), Failure.UNREADABLE),
    ],
)
async def test_every_way_a_feed_can_fail_is_its_own_kind(respond, kind):
    with pytest.raises(FetchFailed) as failed:
        await client_for(respond).fetch(SOURCE)

    assert failed.value.kind is kind


async def test_no_answer_at_all_is_unreachable():
    def handler(request):
        raise httpx.ConnectTimeout("timed out")

    with pytest.raises(FetchFailed) as failed:
        await client_for(handler).fetch(SOURCE)

    assert failed.value.kind is Failure.UNREACHABLE


async def test_validators_of_an_answer_that_could_not_be_read_are_not_kept():
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, content=b"<html/>", headers={"ETag": '"bad"'})

    client = client_for(handler)
    for _ in range(2):
        with pytest.raises(FetchFailed):
            await client.fetch(SOURCE)

    assert "If-None-Match" not in seen[1].headers
