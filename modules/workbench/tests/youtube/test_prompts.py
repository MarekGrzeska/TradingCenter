"""Prompts as data: what the operator may do with them, and that the loop reads a film by the prompt its source holds."""

from __future__ import annotations

from datetime import timedelta

import pytest

from youtube_data import prompts, store, watchlist
from youtube_data.analysis import Analysis, Reading
from youtube_data.providers.base import VideoRef

from .builders import SEEDED_PROMPT_ID
from .harness import GOLD, MARKETS, Rig

pytestmark = pytest.mark.db


class Recording:
    """A model that writes down what it was asked to look for, and answers with it."""

    model = "recording"

    def __init__(self) -> None:
        self.asked: list[tuple[str, str]] = []

    async def read(self, film, transcript, *, prompt):
        self.asked.append((film.video_id, prompt))
        return Analysis(reading=Reading(summary_pl="s", text=f"by: {prompt}", impact_score=3), model=self.model)


def _unheard(rig: Rig) -> VideoRef:
    return VideoRef(
        video_id="unheard01",
        channel_id=GOLD,
        channel_title="Gold",
        title="not yet transcribed",
        published_at=rig.clock.now() - timedelta(hours=1),
    )


async def test_the_seeded_prompt_is_edited_like_any_other_and_cannot_be_deleted(pool) -> None:
    edited = await prompts.update(pool, SEEDED_PROMPT_ID, name=None, body="Only what moves gold.")

    assert edited is not None and edited.version == 2 and edited.seeded
    with pytest.raises(prompts.PromptRefused, match="cannot be deleted"):
        await prompts.delete(pool, SEEDED_PROMPT_ID)
    async with pool.acquire() as conn:
        assert [p.id for p in await store.list_prompts(conn)] == [SEEDED_PROMPT_ID]


async def test_a_name_in_use_is_refused_in_any_case_and_is_free_again_once_deleted(pool) -> None:
    created = await prompts.create(pool, name="Technical", body="Levels only.")

    with pytest.raises(prompts.PromptRefused, match="already exists"):
        await prompts.create(pool, name="technical", body="Other.")
    with pytest.raises(prompts.PromptRefused, match="already exists"):
        await prompts.update(pool, created.id, name="rynkowy", body=None)

    assert await prompts.delete(pool, created.id)
    assert (await prompts.create(pool, name="Technical", body="Again.")).id != created.id


@pytest.mark.parametrize(
    ("name", "body"), [("  ", "text"), ("x" * 81, "text"), ("ok", "  "), ("ok", "x" * 8001)], ids=["blank", "long-name", "blank-body", "long-body"]
)
async def test_a_prompt_has_a_name_and_a_text_of_a_known_length(pool, name, body) -> None:
    with pytest.raises(prompts.PromptRefused):
        await prompts.create(pool, name=name, body=body)


async def test_new_words_make_a_new_version_and_a_new_name_or_the_same_words_make_none(pool) -> None:
    created = await prompts.create(pool, name="Technical", body="Levels only.")

    renamed = await prompts.update(pool, created.id, name="Levels", body="Levels only.")
    reworded = await prompts.update(pool, created.id, name=None, body="Levels and volume.")

    assert renamed is not None and (renamed.name, renamed.version) == ("Levels", 1)
    assert reworded is not None and (reworded.version, reworded.body) == (2, "Levels and volume.")
    assert await prompts.update(pool, 99_999, name="x", body=None) is None


async def test_a_prompt_a_channel_reads_by_cannot_be_deleted_and_the_refusal_names_it(pool) -> None:
    rig = Rig(pool)
    created = await prompts.create(pool, name="Technical", body="Levels only.")
    await watchlist.follow_channel(pool, rig.providers.source, rig.settings, GOLD, added_by="operator", prompt=created.id)
    await watchlist.add_topic(pool, rig.settings, "bitcoin", added_by="operator", prompt="technical")

    with pytest.raises(prompts.PromptRefused) as refused:
        await prompts.delete(pool, created.id)

    assert "Sim" in str(refused.value) and "bitcoin" in str(refused.value)


async def test_a_deleted_prompt_leaves_the_offer_but_not_the_readings_it_made(pool) -> None:
    rig = Rig(pool)
    created = await prompts.create(pool, name="Technical", body="Levels only.")
    await watchlist.follow_channel(pool, rig.providers.source, rig.settings, GOLD, added_by="operator", prompt=created.id)
    await rig.tick()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE channels SET prompt_id = $1", SEEDED_PROMPT_ID)

    assert await prompts.delete(pool, created.id)

    async with pool.acquire() as conn:
        assert [p.name for p in await store.list_prompts(conn)] == ["Rynkowy"]
        film = await store.get_film(conn, "simfilm0001")
    assert film is not None and [r.prompt_name for r in film.readings] == ["Technical"]
    with pytest.raises(watchlist.WatchlistRefused, match="no prompt"):
        await watchlist.add_topic(pool, rig.settings, "gold", added_by="operator", prompt=created.id)


async def test_a_source_without_a_prompt_takes_the_seeded_one_and_an_unknown_prompt_is_refused(pool) -> None:
    rig = Rig(pool)

    followed = await watchlist.follow_channel(pool, rig.providers.source, rig.settings, GOLD, added_by="agent")
    with pytest.raises(watchlist.WatchlistRefused, match="no prompt"):
        await watchlist.follow_channel(pool, rig.providers.source, rig.settings, MARKETS, added_by="agent", prompt="nope")

    assert followed.channel.prompt_id == SEEDED_PROMPT_ID


async def test_a_film_is_read_by_the_prompt_its_channel_held_when_it_was_noticed(pool) -> None:
    recording = Recording()
    rig = Rig(pool, analyser=recording)  # type: ignore[arg-type]
    technical = await prompts.create(pool, name="Technical", body="Levels only.")
    await watchlist.follow_channel(pool, rig.providers.source, rig.settings, GOLD, added_by="operator", prompt=technical.id)

    await rig.tick()

    assert recording.asked and {asked for _, asked in recording.asked} == {"Levels only."}
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT prompt_id, prompt_version FROM readings WHERE video_id = 'simfilm0001'")
        await store.update_channel(conn, GOLD, prompt_id=SEEDED_PROMPT_ID)
        film = await store.get_video(conn, "simfilm0001")
    assert (row["prompt_id"], row["prompt_version"]) == (technical.id, 1)
    assert film is not None and film.prompt_id == technical.id, "a new prompt is for films noticed from now on"


async def test_a_reading_names_the_version_it_was_made_by_after_the_words_change(pool) -> None:
    recording = Recording()
    rig = Rig(pool, analyser=recording)  # type: ignore[arg-type]
    await watchlist.follow_channel(pool, rig.providers.source, rig.settings, GOLD, added_by="operator")
    await rig.tick()

    await prompts.update(pool, SEEDED_PROMPT_ID, name=None, body="Something else.")

    async with pool.acquire() as conn:
        assert await conn.fetchval("SELECT prompt_version FROM readings WHERE video_id = 'simfilm0001'") == 1
        assert (await store.seeded_prompt(conn)).version == 2


async def test_another_prompt_reads_a_film_again_without_asking_for_its_words_or_moving_it(pool) -> None:
    recording = Recording()
    rig = Rig(pool, analyser=recording)  # type: ignore[arg-type]
    await watchlist.follow_channel(pool, rig.providers.source, rig.settings, GOLD, added_by="operator")
    await rig.tick()
    state_before = (await rig.states())["simfilm0001"]
    listened = await rig.used(rig.providers.transcriber.name, "sim_video_seconds")
    technical = await prompts.create(pool, name="Technical", body="Levels only.")

    prompt_id = await prompts.order_reading(pool, rig.settings, rig.clock, "simfilm0001", technical.id)
    await rig.ingest.read_with("simfilm0001", prompt_id)

    async with pool.acquire() as conn:
        film = await store.get_film(conn, "simfilm0001")
    assert film is not None and [r.prompt_name for r in film.readings] == ["Rynkowy", "Technical"]
    assert film.reading is not None and film.reading.prompt_name == "Rynkowy", "the film's own prompt stays its own"
    assert (await rig.states())["simfilm0001"] == state_before
    assert await rig.used(rig.providers.transcriber.name, "sim_video_seconds") == listened


async def test_a_reading_by_another_prompt_is_refused_for_a_film_without_words_or_when_the_days_tokens_are_spent(pool) -> None:
    rig = Rig(pool, daily_token_limit=1)
    await watchlist.follow_channel(pool, rig.providers.source, rig.settings, GOLD, added_by="operator")
    await rig.tick()
    technical = await prompts.create(pool, name="Technical", body="Levels only.")

    async with pool.acquire() as conn:
        await store.upsert_films(conn, [store.Discovery(_unheard(rig), "manual", SEEDED_PROMPT_ID)])
    with pytest.raises(prompts.PromptRefused, match="no transcript"):
        await prompts.order_reading(pool, rig.settings, rig.clock, "unheard01", technical.id)
    with pytest.raises(prompts.PromptRefused, match="no film"):
        await prompts.order_reading(pool, rig.settings, rig.clock, "nothing", technical.id)
    with pytest.raises(prompts.PromptRefused, match="tokens are spent"):
        await prompts.order_reading(pool, rig.settings, rig.clock, "simfilm0001", technical.id)
