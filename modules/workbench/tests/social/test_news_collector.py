"""The news loop against a real database and a scripted HTTP transport: what one pass stores, what a dead
feed does to the rest, and that a pass only counts when it happened."""

from __future__ import annotations

from datetime import timedelta

import httpx
import pytest
from tc_runtime.liveness import LoopHeartbeat

from social_data.news import store
from social_data.news.collector import NewsCollector
from social_data.news.fetch import FeedClient
from social_data.news.sources import NewsSource

from .builders import NOON
from .test_news_feed import FIXTURES

pytestmark = pytest.mark.db

GOOD = NewsSource("good", "A Publisher", "https://good.example/rss", 120)
DEAD = NewsSource("dead", "Nobody", "https://dead.example/rss", 120)
FEED = (FIXTURES / "news_rss.xml").read_bytes()


class Clock:
    def __init__(self):
        self.now = NOON

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)


def collector(pool, clock, handler, *sources, retention=timedelta(days=28), heartbeat=None):
    client = FeedClient(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    return NewsCollector(
        pool,
        client,
        sources,
        tick_seconds=30,
        retention=retention,
        clock=clock,
        heartbeat=heartbeat,
    )


def serve(request):
    if request.url.host == "dead.example":
        return httpx.Response(403)
    return httpx.Response(200, content=FEED)


async def declared(pool, loop, *sources):
    async with pool.acquire() as conn:
        await store.declare_sources(conn, [s.id for s in sources])
    return loop


async def read_all(pool):
    async with pool.acquire() as conn:
        items = await store.items_in_window(
            conn,
            start=NOON - timedelta(days=60),
            end=NOON + timedelta(days=60),
            sources=None,
            text=None,
            limit=100,
        )
        return items, {row.source: row for row in await store.source_rows(conn)}


async def test_a_feed_that_refuses_costs_only_itself(pool):
    clock = Clock()
    loop = await declared(pool, collector(pool, clock, serve, GOOD, DEAD), GOOD, DEAD)

    await loop.tick()

    items, rows = await read_all(pool)
    assert {item.source for item in items} == {"good"}
    assert rows["good"].last_success_at == NOON
    assert rows["dead"].last_success_at is None
    assert rows["dead"].last_failure == "refused: HTTP 403"


async def test_the_second_fetch_measures_what_the_first_only_found(pool):
    clock = Clock()
    loop = await declared(pool, collector(pool, clock, serve, GOOD), GOOD)

    await loop.tick()
    clock.advance(minutes=2)
    await loop.tick()

    items, _ = await read_all(pool)
    assert {item.previous_fetch_at for item in items} == {None}
    assert len(items) == 3


async def test_a_feed_is_not_asked_again_before_its_interval(pool):
    clock = Clock()
    asked = []

    def handler(request):
        asked.append(clock.now)
        return httpx.Response(200, content=FEED)

    loop = await declared(pool, collector(pool, clock, handler, GOOD), GOOD)

    for _ in range(3):
        await loop.tick()
        clock.advance(seconds=30)
    clock.advance(seconds=30)
    await loop.tick()

    assert asked == [NOON, NOON + timedelta(seconds=120)]


async def test_not_modified_is_a_successful_fetch(pool):
    clock = Clock()

    def handler(request):
        if request.headers.get("If-None-Match"):
            return httpx.Response(304)
        return httpx.Response(200, content=FEED, headers={"ETag": '"v"'})

    loop = await declared(pool, collector(pool, clock, handler, GOOD), GOOD)
    await loop.tick()
    clock.advance(minutes=2)
    await loop.tick()

    _, rows = await read_all(pool)
    assert rows["good"].last_success_at == NOON + timedelta(minutes=2)


async def test_the_sweep_lets_old_headlines_go_but_not_kept_ones(pool):
    clock = Clock()
    loop = await declared(pool, collector(pool, clock, serve, GOOD), GOOD)
    await loop.tick()
    async with pool.acquire() as conn:
        await store.set_kept(conn, "good", "guid-talks", keep=True, at=NOON)

    clock.advance(days=29)
    await loop.tick()

    items, _ = await read_all(pool)
    assert [item.external_id for item in items] == ["guid-talks"]


async def test_a_pass_that_raised_does_not_beat_the_heartbeat(pool, monkeypatch):
    clock = Clock()
    heartbeat = LoopHeartbeat("news", expected_seconds=30)
    loop = collector(pool, clock, serve, GOOD, heartbeat=heartbeat)

    async def broken():
        raise RuntimeError("database gone")

    monkeypatch.setattr(loop, "tick", broken)
    loop._tick = 0  # the loop under test sleeps between passes; do not make it wait
    await loop.start()
    import asyncio

    await asyncio.sleep(0.05)
    await loop.stop()

    assert not heartbeat.has_run


async def test_the_loop_collects_by_itself_without_anybody_asking(pool):
    import asyncio

    clock = Clock()
    loop = collector(pool, clock, serve, GOOD)
    loop._tick = 0.01
    await loop.start()
    try:
        for _ in range(100):
            await asyncio.sleep(0.02)
            if (await read_all(pool))[0]:
                break
    finally:
        await loop.stop()

    assert len((await read_all(pool))[0]) == 3
