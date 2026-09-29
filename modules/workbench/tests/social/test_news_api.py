"""The news contract over HTTP: that the state reaches the wire and a refusal says why. The rules — windows,
narrowing, retention, the delay's bounds — are tested where they live, in the store and in `latency`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from social_data.news import store
from social_data.news.sources import SOURCES

from .builders import feed_item

pytestmark = pytest.mark.db

SOURCE = SOURCES[0].id


async def collected(pool, items, *, source=SOURCE, first_fetch_minutes_ago=3, seen_minutes_ago=1):
    """Two fetches of one feed: an empty first, so the items of the second are measured rather than found."""
    now = datetime.now(UTC)
    async with pool.acquire() as conn:
        await store.declare_sources(conn, [source])
        await store.record_success(
            conn,
            source,
            at=now - timedelta(minutes=first_fetch_minutes_ago),
            newest_published_at=None,
        )
        previous = await store.previous_success(conn, source)
        await store.insert_items(
            conn,
            source,
            items,
            seen_at=now - timedelta(minutes=seen_minutes_ago),
            previous_fetch_at=previous,
        )
        await store.record_success(
            conn, source, at=now - timedelta(minutes=seen_minutes_ago), newest_published_at=None
        )


def published(minutes_ago):
    return datetime.now(UTC) - timedelta(minutes=minutes_ago)


async def test_a_headline_reaches_the_wire_with_both_bounds_of_its_delay(api, pool):
    await collected(pool, [feed_item("a", published_at=published(10))])

    [item] = (await api.get("/news", params={"hours": 6})).json()["items"]

    assert item["first_seen_at"] and item["previous_fetch_at"]
    assert item["delay_min_seconds"] == pytest.approx(7 * 60, abs=2)
    assert item["delay_max_seconds"] == pytest.approx(9 * 60, abs=2)
    assert item["delay_unmeasured"] is None
    assert item["kept_at"] is None and item["expires_at"] is not None


async def test_a_headline_without_a_time_carries_the_fields_and_says_why(api, pool):
    await collected(pool, [feed_item("a", published_at=None)])

    [item] = (await api.get("/news", params={"hours": 6})).json()["items"]

    assert (item["published_at"], item["delay_min_seconds"], item["delay_max_seconds"]) == (
        None,
        None,
        None,
    )
    assert item["delay_unmeasured"] == "no_publish_time"


async def test_a_window_bigger_than_the_limit_says_it_is_cut_and_keeps_the_newest(api, pool):
    await collected(pool, [feed_item(str(n), published_at=published(n + 1)) for n in range(5)])

    body = (await api.get("/news", params={"hours": 6, "limit": 3})).json()

    assert (body["count"], body["truncated"]) == (3, True)
    assert [item["external_id"] for item in body["items"]] == ["0", "1", "2"]


async def test_a_window_that_ends_before_it_starts_is_refused_with_a_reason(api):
    now = datetime.now(UTC)

    answer = await api.get(
        "/news", params={"since": now.isoformat(), "until": (now - timedelta(hours=2)).isoformat()}
    )

    assert answer.status_code == 422
    assert answer.json()["detail"]["cause"] == "request"


async def test_keeping_a_headline_whose_identifier_is_a_url_reaches_it_and_the_kept_list_finds_it(
    api, pool
):
    url_id = "https://www.example.com/news/2026/9/29/talks?utm=1"
    await collected(pool, [feed_item(url_id, title="Talks", published_at=published(50 * 24 * 60))])

    kept = await api.put("/news/keep", json={"source": SOURCE, "external_id": url_id, "keep": True})
    listed = (await api.get("/news", params={"kept": True})).json()
    released = await api.put(
        "/news/keep", json={"source": SOURCE, "external_id": url_id, "keep": False}
    )

    assert kept.status_code == 200
    assert kept.json()["kept_at"] is not None and kept.json()["expires_at"] is None
    assert kept.json()["title"] == "Talks"
    assert [item["external_id"] for item in listed["items"]] == [url_id]
    assert listed["window_from"] is None
    assert released.json()["kept_at"] is None


async def test_keeping_a_headline_that_is_not_there_is_refused_not_created(api):
    answer = await api.put(
        "/news/keep", json={"source": SOURCE, "external_id": "nothing", "keep": True}
    )

    assert answer.status_code == 404


async def test_the_sources_lists_every_declared_feed_including_one_that_never_answered(api, pool):
    await collected(pool, [feed_item("a", published_at=published(10))])
    async with pool.acquire() as conn:
        await store.declare_sources(conn, [source.id for source in SOURCES])

    body = (await api.get("/news/sources")).json()
    by_id = {source["source"]: source for source in body["sources"]}

    assert set(by_id) == {source.id for source in SOURCES}
    assert by_id[SOURCE]["status"] == "ok" and by_id[SOURCE]["items_24h"] == 1
    assert by_id[SOURCE]["delay_max_median_seconds"] == pytest.approx(9 * 60, abs=2)
    never = by_id[SOURCES[1].id]
    assert never["status"] == "pending" and never["last_success_at"] is None
    assert never["delay_max_median_seconds"] is None


async def test_a_feed_whose_latest_fetch_failed_is_named_failing_with_its_reason(api, pool):
    await collected(pool, [feed_item("a")])
    async with pool.acquire() as conn:
        await store.record_failure(conn, SOURCE, at=datetime.now(UTC), reason="refused: HTTP 403")

    body = (await api.get("/news/sources")).json()
    failing = next(source for source in body["sources"] if source["source"] == SOURCE)

    assert failing["status"] == "failing"
    assert failing["last_failure"] == "refused: HTTP 403"
    assert failing["last_success_at"] is not None


async def test_reading_the_news_adds_nothing_to_the_archive(api, pool):
    await collected(pool, [feed_item("a", published_at=published(10))])

    async def count():
        async with pool.acquire() as conn:
            return await conn.fetchval("SELECT count(*) FROM news_items")

    before = await count()
    for path in ("/news", "/news/sources"):
        await api.get(path)

    assert await count() == before
