"""The statements, against a real PostgreSQL. What is under test here is the schema as much as the
SQL: identity is a pair, a reading carries its stamp, and the bill survives the reading."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import asyncpg
import pytest
from builders import NOON, TRUTH_SOCIAL, raw_post

from social_data import store
from social_data.models import Operation

pytestmark = pytest.mark.db

WINDOW = (NOON - timedelta(days=1), NOON + timedelta(days=1))


async def test_the_same_post_collected_twice_is_stored_once(db):
    first = await store.insert_new_posts(db, [raw_post("a"), raw_post("b")])
    second = await store.insert_new_posts(db, [raw_post("a"), raw_post("b"), raw_post("c")])

    assert (first, second) == (2, 1)
    assert await store.count_in_window(db, start=WINDOW[0], end=WINDOW[1]) == 3


async def test_a_stored_post_keeps_the_text_it_was_collected_with(db):
    await store.insert_new_posts(db, [raw_post("a", content="first text")])
    await store.insert_new_posts(db, [raw_post("a", content="rewritten later")])

    post = await store.post_by_external_id(db, TRUTH_SOCIAL, "a")
    assert post is not None
    assert post.content == "first text"


async def test_two_sources_may_number_their_posts_the_same_way(db):
    inserted = await store.insert_new_posts(
        db, [raw_post("1"), raw_post("1", source="other_source")]
    )

    assert inserted == 2
    assert await store.post_by_external_id(db, TRUTH_SOCIAL, "1") is not None
    assert await store.post_by_external_id(db, "other_source", "1") is not None


async def test_a_window_answers_newest_first_and_excludes_what_falls_outside(db):
    await store.insert_new_posts(
        db,
        [
            raw_post("old", published_at=NOON - timedelta(days=3)),
            raw_post("early", published_at=NOON - timedelta(hours=2)),
            raw_post("late", published_at=NOON),
        ],
    )

    found = await store.posts_in_window(db, start=NOON - timedelta(hours=5), end=NOON)

    assert [post.external_id for post in found] == ["late", "early"]


async def test_a_window_narrows_by_source_score_and_topic(db):
    await store.insert_new_posts(db, [raw_post("scored"), raw_post("unscored")])
    scored = await store.post_by_external_id(db, TRUTH_SOCIAL, "scored")
    assert scored is not None
    await store.save_analysis(db, scored.id, topics=["tariffs", "china"], score=8, model="m")

    by_score = await store.posts_in_window(db, start=WINDOW[0], end=WINDOW[1], min_score=6)
    by_topic = await store.posts_in_window(db, start=WINDOW[0], end=WINDOW[1], topic="china")
    by_other_source = await store.posts_in_window(
        db, start=WINDOW[0], end=WINDOW[1], source="nobody"
    )

    assert [post.external_id for post in by_score] == ["scored"]
    assert [post.external_id for post in by_topic] == ["scored"]
    assert by_other_source == []


async def test_a_reading_is_saved_with_its_stamp_and_overwritten_whole(db):
    await store.insert_new_posts(db, [raw_post("a")])
    post = await store.post_by_external_id(db, TRUTH_SOCIAL, "a")
    assert post is not None

    await store.save_analysis(db, post.id, topics=["tariffs"], score=7, model="first-model")
    await store.save_translation(db, post.id, text="CŁA NADCHODZĄ.", model="translator")
    await store.save_analysis(db, post.id, topics=["trade"], score=3, model="second-model")

    reread = await store.post_by_external_id(db, TRUTH_SOCIAL, "a")
    assert reread is not None
    assert (reread.impact_score, reread.analysed_model, reread.topics) == (
        3,
        "second-model",
        ("trade",),
    )
    assert reread.analysed_at is not None
    assert (reread.translated_content, reread.translated_model) == ("CŁA NADCHODZĄ.", "translator")


async def test_the_bill_survives_the_reading_it_paid_for(db):
    await store.insert_new_posts(db, [raw_post("a")])
    post = await store.post_by_external_id(db, TRUTH_SOCIAL, "a")
    assert post is not None

    await store.record_usage(
        db, post.id, operation=Operation.ANALYSIS, model="first", input_tokens=10, output_tokens=2
    )
    await store.save_analysis(db, post.id, topics=["t"], score=5, model="first")
    await store.record_usage(
        db, post.id, operation=Operation.ANALYSIS, model="second", input_tokens=11, output_tokens=3
    )
    await store.save_analysis(db, post.id, topics=["t"], score=6, model="second")

    models = await db.fetch("SELECT model FROM model_usage WHERE post_id = $1 ORDER BY id", post.id)
    assert [row["model"] for row in models] == ["first", "second"]


async def test_a_score_outside_one_to_ten_is_refused_by_the_schema(db):
    await store.insert_new_posts(db, [raw_post("a")])
    post = await store.post_by_external_id(db, TRUTH_SOCIAL, "a")
    assert post is not None

    with pytest.raises(asyncpg.CheckViolationError):
        await store.save_analysis(db, post.id, topics=["t"], score=11, model="m")


async def test_posts_awaiting_a_reading_are_the_unread_ones_inside_the_window(db):
    await store.insert_new_posts(
        db,
        [
            raw_post("recent"),
            raw_post("stale", published_at=NOON - timedelta(days=5)),
        ],
    )
    recent = await store.post_by_external_id(db, TRUTH_SOCIAL, "recent")
    assert recent is not None

    awaiting = await store.posts_awaiting_analysis(db, since=NOON - timedelta(hours=1), limit=10)
    assert [post.external_id for post in awaiting] == ["recent"]

    await store.save_analysis(db, recent.id, topics=["t"], score=4, model="m")
    assert await store.posts_awaiting_analysis(db, since=NOON - timedelta(hours=1), limit=10) == []


async def test_collection_start_is_written_once_and_a_failure_does_not_move_the_success(db):
    started = datetime.now(UTC) - timedelta(days=2)
    first = await store.begin_collecting(db, TRUTH_SOCIAL, at=started)
    again = await store.begin_collecting(db, TRUTH_SOCIAL)

    assert first == again == started

    success_at = datetime.now(UTC) - timedelta(minutes=5)
    await store.record_collection_success(db, TRUTH_SOCIAL, at=success_at)
    await store.record_collection_failure(
        db, TRUTH_SOCIAL, at=datetime.now(UTC), reason="feed did not answer"
    )

    [state] = await store.collection_states(db)
    assert state.last_success_at == success_at
    assert state.consecutive_failures == 1
    assert state.last_failure_reason == "feed did not answer"
