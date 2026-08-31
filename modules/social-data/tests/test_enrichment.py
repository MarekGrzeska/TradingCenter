"""The reading a model produces: stamped, bounded, overwritten — and never at the cost of the pass
that collected the post."""

from __future__ import annotations

from datetime import timedelta

import pytest
from builders import NOON, TRUTH_SOCIAL, raw_post
from fakes import FakeModel, FakeSource

from social_data import enrichment, store
from social_data.enrichment import Enrichment, ModelUnusable, analysis_from
from social_data.ingest import Ingest

WINDOW_STARTS = NOON - timedelta(hours=1)
JUST_AFTER_NOON = NOON + timedelta(minutes=1)


def reading(payload: str):
    return analysis_from(payload, model="m", input_tokens=1, output_tokens=1)


async def collect(pool, posts) -> None:
    """The posts in the archive, put there the way the module puts them there."""
    source = FakeSource(posts)
    await Ingest(
        pool, [source], interval_seconds=60, window_hours=24, clock=lambda: JUST_AFTER_NOON
    ).collect(source)


def test_a_readable_answer_becomes_a_reading():
    result = reading('{"topics": ["tariffs", " china "], "impact_score": 8}')

    assert (result.score, result.topics) == (8, ("tariffs", "china"))


@pytest.mark.parametrize(
    "payload",
    [
        "not json at all",
        '["tariffs", 8]',
        '{"topics": ["a"], "impact_score": 0}',
        '{"topics": ["a"], "impact_score": 11}',
        '{"topics": ["a"], "impact_score": "high"}',
        '{"topics": "tariffs", "impact_score": 5}',
    ],
)
def test_an_answer_this_module_will_not_store_is_refused(payload):
    with pytest.raises(ModelUnusable):
        reading(payload)


def test_a_model_answering_with_forty_topics_is_trimmed():
    many = ", ".join(f'"t{n}"' for n in range(40))

    assert len(reading(f'{{"topics": [{many}], "impact_score": 5}}').topics) == enrichment.MAX_TOPICS


def test_without_a_key_there_is_no_enrichment_and_that_is_not_a_refusal(settings):
    unconfigured = settings.model_copy(update={"openai_api_key": None})
    configured = settings.model_copy(update={"openai_api_key": "sk-test"})

    assert enrichment.build(pool=None, settings=unconfigured) is None
    assert enrichment.build(pool=None, settings=configured) is not None


@pytest.mark.db
async def test_a_reading_is_written_with_the_model_that_produced_it(pool):
    await collect(pool, [raw_post("a")])

    await Enrichment(pool, FakeModel(), batch_limit=10).run(WINDOW_STARTS)

    async with pool.acquire() as conn:
        post = await store.post_by_external_id(conn, TRUTH_SOCIAL, "a")
    assert post is not None
    assert (post.impact_score, post.analysed_model) == (8, "fake-analyst")
    assert post.topics == ("tariffs", "china")
    assert (post.translated_content, post.translated_model) == ("CŁA NADCHODZĄ.", "fake-translator")
    assert post.analysed_at is not None and post.translated_at is not None


@pytest.mark.db
async def test_the_bill_is_written_beside_the_reading(pool):
    await collect(pool, [raw_post("a")])

    await Enrichment(pool, FakeModel(), batch_limit=10).run(WINDOW_STARTS)

    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT operation, model FROM model_usage")
    assert {(row["operation"], row["model"]) for row in rows} == {
        ("translation", "fake-translator"),
        ("analysis", "fake-analyst"),
    }


@pytest.mark.db
async def test_a_post_already_read_is_not_read_again(pool):
    await collect(pool, [raw_post("a")])
    model = FakeModel()
    enricher = Enrichment(pool, model, batch_limit=10)

    await enricher.run(WINDOW_STARTS)
    await enricher.run(WINDOW_STARTS)

    assert (model.translations, model.analyses) == (1, 1)


@pytest.mark.db
async def test_one_posts_failure_costs_that_post_only(pool):
    await collect(pool, [raw_post("a"), raw_post("b")])

    await Enrichment(
        pool, FakeModel(raises_once=RuntimeError("the model refused")), batch_limit=10
    ).run(WINDOW_STARTS)

    async with pool.acquire() as conn:
        still_waiting = await store.posts_awaiting_translation(conn, since=WINDOW_STARTS, limit=10)
    assert len(still_waiting) == 1


@pytest.mark.db
async def test_a_model_that_never_answers_leaves_every_post_collected_and_unread(pool):
    await collect(pool, [raw_post("a")])

    written = await Enrichment(
        pool, FakeModel(raises=RuntimeError("the model is down")), batch_limit=10
    ).run(WINDOW_STARTS)

    assert written == (0, 0)
    async with pool.acquire() as conn:
        post = await store.post_by_external_id(conn, TRUTH_SOCIAL, "a")
    assert post is not None
    assert post.impact_score is None and post.translated_content is None


@pytest.mark.db
async def test_a_pass_stops_at_the_ceiling_on_what_it_may_spend(pool):
    await collect(pool, [raw_post(str(n)) for n in range(5)])
    model = FakeModel()

    await Enrichment(pool, model, batch_limit=2).run(WINDOW_STARTS)

    assert (model.translations, model.analyses) == (2, 2)


@pytest.mark.db
async def test_posts_older_than_the_window_are_never_read(pool):
    async with pool.acquire() as conn:
        await store.insert_new_posts(conn, [raw_post("old", published_at=NOON - timedelta(days=3))])
    model = FakeModel()

    await Enrichment(pool, model, batch_limit=10).run(WINDOW_STARTS)

    assert (model.translations, model.analyses) == (0, 0)


@pytest.mark.db
async def test_a_model_failure_does_not_stop_the_collection_pass(pool):
    source = FakeSource([raw_post("a")])

    async def explode(since):
        raise RuntimeError("the model is down")

    ingest = Ingest(
        pool,
        [source],
        interval_seconds=60,
        window_hours=24,
        enrich=explode,
        clock=lambda: JUST_AFTER_NOON,
    )
    [result] = await ingest.tick()

    assert result.inserted == 1
    assert result.succeeded
