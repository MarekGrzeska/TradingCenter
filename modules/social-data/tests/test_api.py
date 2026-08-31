"""The contract over HTTP: that the state reaches the wire, and that a refusal says why.

One test per route, not the whole matrix — windows, ordering and narrowing are tested against the
store, where the rules actually live."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from builders import TRUTH_SOCIAL, raw_post

from social_data import store

pytestmark = pytest.mark.db


async def stored(pool, posts):
    async with pool.acquire() as conn:
        await store.insert_new_posts(conn, posts)
        return await store.collection_states(conn)


async def test_a_window_answers_with_its_own_edges_and_the_posts_in_it(api, pool):
    await stored(pool, [raw_post("a", minutes_ago=10), raw_post("old", minutes_ago=60 * 40)])

    answer = await api.get("/posts", params={"hours": 24})

    assert answer.status_code == 200
    body = answer.json()
    assert body["count"] == 1
    assert [post["external_id"] for post in body["posts"]] == ["a"]
    assert body["window_from"] < body["window_to"]


async def test_a_reading_reaches_the_wire_with_the_model_that_produced_it(api, pool):
    await stored(pool, [raw_post("a", minutes_ago=10)])
    async with pool.acquire() as conn:
        post = await store.post_by_external_id(conn, TRUTH_SOCIAL, "a")
        assert post is not None
        await store.save_analysis(conn, post.id, topics=["tariffs"], score=9, model="an-analyst")
        await store.save_translation(conn, post.id, text="CŁA.", model="a-translator")

    [answered] = (await api.get("/posts", params={"hours": 24})).json()["posts"]

    assert (answered["impact_score"], answered["analysed_model"]) == (9, "an-analyst")
    assert (answered["translated_content"], answered["translated_model"]) == ("CŁA.", "a-translator")
    assert answered["topics"] == ["tariffs"]


async def test_a_post_without_a_reading_carries_the_fields_anyway(api, pool):
    await stored(pool, [raw_post("a", minutes_ago=10)])

    [answered] = (await api.get("/posts", params={"hours": 24})).json()["posts"]

    assert answered["impact_score"] is None
    assert answered["translated_content"] is None
    assert answered["analysed_model"] is None
    assert answered["topics"] == []


async def test_a_window_that_ends_before_it_starts_is_refused_with_a_reason(api):
    now = datetime.now(UTC)

    answer = await api.get(
        "/posts",
        params={"since": now.isoformat(), "until": (now - timedelta(hours=2)).isoformat()},
    )

    assert answer.status_code == 422
    assert answer.json()["detail"]["cause"] == "request"


async def test_one_post_is_read_by_the_pair_that_identifies_it(api, pool):
    await stored(pool, [raw_post("a", minutes_ago=10)])

    found = await api.get(f"/posts/{TRUTH_SOCIAL}/a")
    missing = await api.get(f"/posts/{TRUTH_SOCIAL}/nothing-like-this")

    assert found.status_code == 200
    assert found.json()["external_id"] == "a"
    assert missing.status_code == 404


async def test_the_state_says_since_when_it_collects_and_whether_a_model_is_configured(api, pool):
    async with pool.acquire() as conn:
        await store.begin_collecting(conn, TRUTH_SOCIAL)
        await store.record_collection_success(conn, TRUTH_SOCIAL, at=datetime.now(UTC))
    await stored(pool, [raw_post("a", minutes_ago=10)])

    body = (await api.get("/state")).json()

    assert body["model_configured"] is False
    assert body["posts_in_window"] == 1
    [source] = body["sources"]
    assert source["source"] == TRUTH_SOCIAL
    assert source["stale"] is False
    # What a window before this moment is answered with: nothing, and the reason, because there
    # is no backfill and nothing older will ever arrive.
    assert source["collecting_since"] is not None


async def test_an_archive_that_has_not_collected_for_a_long_time_says_so(api, pool):
    async with pool.acquire() as conn:
        await store.begin_collecting(conn, TRUTH_SOCIAL, at=datetime.now(UTC) - timedelta(days=2))
        await store.record_collection_success(
            conn, TRUTH_SOCIAL, at=datetime.now(UTC) - timedelta(hours=6)
        )
        await store.record_collection_failure(
            conn, TRUTH_SOCIAL, at=datetime.now(UTC), reason="the feed did not answer"
        )

    [source] = (await api.get("/state")).json()["sources"]

    assert source["stale"] is True
    assert source["last_failure_reason"] == "the feed did not answer"
    assert source["consecutive_failures"] == 1


async def test_the_contract_publishes_no_route_that_writes(api):
    document = (await api.get("/openapi.json")).json()

    methods = {
        method.upper()
        for path in document["paths"].values()
        for method in path
        if method in ("get", "post", "put", "patch", "delete")
    }
    assert methods == {"GET"}
