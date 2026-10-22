"""The queries the loop stands on. What is checked is the behaviour the loop needs from them, and one cost rule: a film seen
again writes nothing."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from youtube_data import store
from youtube_data.analysis import Reading
from youtube_data.providers.base import ChannelInfo, VideoRef
from youtube_data.store import Discovery, ProviderState

from .builders import SEEDED_PROMPT_ID

pytestmark = pytest.mark.db

NOW = datetime(2026, 9, 27, 8, 0, tzinfo=UTC)


def film(video_id: str = "v1", **overrides) -> VideoRef:
    return VideoRef(
        video_id=video_id,
        channel_id="UC1",
        channel_title="A Channel",
        title="A film",
        published_at=NOW - timedelta(hours=1),
        **overrides,
    )


def discovery(video_id: str = "v1", origin: str = "channel:UC1", **overrides) -> Discovery:
    return Discovery(film(video_id, **overrides), origin, SEEDED_PROMPT_ID)


async def test_following_a_channel_twice_keeps_what_the_operator_set(db) -> None:
    info = ChannelInfo(channel_id="UC1", title="A Channel")
    first = await store.add_channel(db, info, language="pl", prompt_id=SEEDED_PROMPT_ID, added_by="operator")

    again = await store.add_channel(db, info, language="", prompt_id=SEEDED_PROMPT_ID, added_by="agent")

    assert again == first
    assert again.language == "pl" and again.added_by == "operator"


async def test_pausing_a_channel_is_not_removing_it(db) -> None:
    info = ChannelInfo(channel_id="UC1", title="A Channel")
    await store.add_channel(db, info, language="", prompt_id=SEEDED_PROMPT_ID, added_by="operator")

    paused = await store.update_channel(db, "UC1", active=False)

    assert paused is not None and not paused.active
    assert await store.list_channels(db, active_only=True) == []
    assert len(await store.list_channels(db)) == 1


async def test_a_film_seen_again_is_not_new_and_writes_nothing(db) -> None:
    assert await store.upsert_films(db, [discovery()]) == 1
    version = await db.fetchval("SELECT xmin::text FROM videos WHERE video_id = 'v1'")

    assert await store.upsert_films(db, [discovery()]) == 0

    # A channel's fifteen latest are listed every pass: an upsert that touched each would be four hundred dead rows a day.
    assert await db.fetchval("SELECT xmin::text FROM videos WHERE video_id = 'v1'") == version


async def test_a_film_that_arrives_by_a_second_door_is_one_film_with_both(db) -> None:
    await store.upsert_films(db, [discovery(origin="channel:UC1")])

    assert await store.upsert_films(db, [discovery(origin="topic:7")]) == 0

    video = await store.get_video(db, "v1")
    assert video is not None and video.origins == ("channel:UC1", "topic:7")


async def test_a_length_the_first_sighting_lacked_is_filled_in_and_a_known_one_is_kept(db) -> None:
    await store.upsert_films(db, [discovery()])

    await store.upsert_films(db, [discovery(duration_seconds=600)])
    await store.upsert_films(db, [discovery(duration_seconds=999)])

    video = await store.get_video(db, "v1")
    assert video is not None and video.duration_seconds == 600


async def test_only_films_whose_length_is_known_and_out_of_bounds_are_dropped(db) -> None:
    """A premiere is stored without a length and gets one later; a film already known to be out of bounds is never stored."""
    films = [
        discovery("short", duration_seconds=30),
        discovery("long", duration_seconds=20_000),
        discovery("fine", duration_seconds=600),
        discovery("unknown"),
        discovery("live", live_status="live"),
    ]
    assert await store.upsert_films(db, films, bounds=(60, 10_800)) == 3
    assert {row["video_id"] for row in await db.fetch("SELECT video_id FROM videos")} == {"fine", "unknown", "live"}

    await db.execute("UPDATE videos SET duration_seconds = 30 WHERE video_id = 'unknown'")
    await db.execute(
        "INSERT INTO videos (video_id, title, published_at, origins, state, skip_reason, prompt_id) "
        "VALUES ('old', 'x', now(), ARRAY['manual'], 'skipped', 'older version', $1)",
        SEEDED_PROMPT_ID,
    )

    assert await store.drop_unwanted(db, minimum=60, maximum=10_800) == 2

    assert {row["video_id"] for row in await db.fetch("SELECT video_id FROM videos")} == {"fine", "live"}


async def test_the_queue_holds_what_is_due_and_not_what_is_live_or_finished(db) -> None:
    await store.upsert_films(
        db, [discovery("ready"), discovery("waiting"), discovery("live", live_status="live"), discovery("done")]
    )
    await store.record_no_transcript(db, "waiting", give_up=False, retry_at=NOW + timedelta(hours=1))
    await store.record_no_transcript(db, "done", give_up=True, retry_at=None)

    due = [v.video_id for v in await store.due_for_transcription(db, NOW, 10)]
    later = [v.video_id for v in await store.due_for_transcription(db, NOW + timedelta(hours=2), 10)]

    assert due == ["ready"]
    assert sorted(later) == ["ready", "waiting"]


async def test_a_reading_overwrites_the_last_one_by_the_same_prompt_and_sits_beside_another_prompts(db) -> None:
    await store.upsert_films(db, [discovery()])
    other = await store.create_prompt(db, name="Technical", body="Levels only.")
    reading = Reading(summary_pl="x", text="## Tezy\n- a", impact_score=4)

    await store.save_reading(
        db, "v1", prompt_id=SEEDED_PROMPT_ID, prompt_version=1, reading=reading, model="m1", simulated=False
    )
    await store.save_reading(
        db,
        "v1",
        prompt_id=SEEDED_PROMPT_ID,
        prompt_version=2,
        reading=reading.model_copy(update={"impact_score": 8}),
        model="m2",
        simulated=True,
    )
    await store.save_reading(db, "v1", prompt_id=other.id, prompt_version=1, reading=reading, model="m3", simulated=False)

    rows = await db.fetch("SELECT prompt_id, prompt_version, impact_score, model, simulated FROM readings ORDER BY model")
    assert [(r["prompt_id"], r["prompt_version"], r["impact_score"], r["model"], r["simulated"]) for r in rows] == [
        (SEEDED_PROMPT_ID, 2, 8, "m2", True),
        (other.id, 1, 4, "m3", False),
    ]


async def test_a_film_moves_on_only_by_the_reading_of_its_own_prompt(db) -> None:
    await store.upsert_films(db, [discovery()])
    await db.execute("UPDATE videos SET state = 'transcribed'")
    other = await store.create_prompt(db, name="Technical", body="Levels only.")
    reading = Reading(summary_pl="x", text="t", impact_score=4)

    await store.save_reading(db, "v1", prompt_id=other.id, prompt_version=1, reading=reading, model="m", simulated=False)
    assert (await store.get_video(db, "v1")).state == "transcribed"  # type: ignore[union-attr]

    await store.save_reading(
        db, "v1", prompt_id=SEEDED_PROMPT_ID, prompt_version=1, reading=reading, model="m", simulated=False
    )
    assert (await store.get_video(db, "v1")).state == "analysed"  # type: ignore[union-attr]


async def test_a_list_carries_no_text_and_one_film_carries_every_reading_the_films_own_first(db) -> None:
    await store.upsert_films(db, [discovery()])
    other = await store.create_prompt(db, name="Technical", body="Levels only.")
    for prompt_id, text in ((other.id, "levels"), (SEEDED_PROMPT_ID, "theses")):
        await store.save_reading(
            db,
            "v1",
            prompt_id=prompt_id,
            prompt_version=1,
            reading=Reading(summary_pl="s", text=text, impact_score=3),
            model="m",
            simulated=False,
        )

    (listed,) = await store.list_films(db, start=NOW - timedelta(days=1), end=NOW, limit=10)
    one = await store.get_film(db, "v1")

    assert listed.reading is not None and "text" not in listed.reading.result
    assert one is not None and [r.result["text"] for r in one.readings] == ["theses", "levels"]


async def test_usage_adds_up_within_a_day_and_keeps_days_apart(db) -> None:
    today, tomorrow = NOW.date(), (NOW + timedelta(days=1)).date()

    await store.add_usage(db, {("sim", "sim_units"): 3, ("sim", "sim_credits"): 1}, day=today)
    await store.add_usage(db, {("sim", "sim_units"): 4}, day=today)
    await store.add_usage(db, {("sim", "sim_units"): 9}, day=tomorrow)

    assert await store.usage_on(db, today) == {("sim", "sim_units"): 7, ("sim", "sim_credits"): 1}
    assert await store.usage_on(db, tomorrow) == {("sim", "sim_units"): 9}


async def test_a_provider_is_blocked_until_it_next_answers(db) -> None:
    await store.note_provider(db, "direct", ok=True, at=NOW)
    await store.note_provider(db, "direct", ok=False, at=NOW + timedelta(minutes=1), reason="IpBlocked")
    assert (await store.provider_states(db))["direct"].blocked

    await store.note_provider(db, "direct", ok=True, at=NOW + timedelta(minutes=2))

    assert not (await store.provider_states(db))["direct"].blocked


def test_a_provider_that_was_never_blocked_is_not_blocked() -> None:
    assert not ProviderState("direct", last_ok_at=None, last_blocked_at=None, blocked_reason=None).blocked



async def test_a_channel_filter_is_set_kept_and_taken_off_only_when_asked(db) -> None:
    info = ChannelInfo(channel_id="UC1", title="A Channel")
    added = await store.add_channel(
        db, info, language="", prompt_id=SEEDED_PROMPT_ID, added_by="agent", filter="only macro analyses"
    )
    assert added.filter == "only macro analyses"

    paused = await store.update_channel(db, "UC1", active=False)
    assert paused is not None and paused.filter == "only macro analyses"

    cleared = await store.update_channel(db, "UC1", filter=None)
    assert cleared is not None and cleared.filter is None


async def test_a_filtered_out_film_is_kept_with_its_reason_and_listed_only_when_asked_for(db) -> None:
    kept = Discovery(film("v1"), "channel:UC1", SEEDED_PROMPT_ID)
    turned_away = Discovery(film("v2"), "channel:UC1", SEEDED_PROMPT_ID, filtered_reason="a Q&A with viewers")
    await store.upsert_films(db, [kept, turned_away])

    window = {"start": NOW - timedelta(days=1), "end": NOW, "limit": 10}
    assert [f.video.video_id for f in await store.list_films(db, **window)] == ["v1"]
    only = await store.list_films(db, state="filtered_out", **window)
    assert [(f.video.video_id, f.video.skip_reason) for f in only] == [("v2", "a Q&A with viewers")]
    assert await store.due_for_transcription(db, NOW, 10) == [(await store.get_video(db, "v1"))]


async def test_a_filtered_out_film_seen_again_is_not_stored_again_and_survives_the_drop(db) -> None:
    turned_away = Discovery(film("v2"), "channel:UC1", SEEDED_PROMPT_ID, filtered_reason="a Q&A")
    await store.upsert_films(db, [turned_away])

    assert await store.upsert_films(db, [turned_away]) == 0
    await store.drop_unwanted(db, minimum=180, maximum=4 * 3600)

    assert (await store.get_video(db, "v2")).state == "filtered_out"


async def test_releasing_a_filtered_out_film_puts_it_in_the_queue_and_leaves_any_other_film_alone(db) -> None:
    await store.upsert_films(
        db,
        [
            Discovery(film("v2"), "channel:UC1", SEEDED_PROMPT_ID, filtered_reason="a Q&A"),
            discovery("v1"),
        ],
    )

    assert await store.release_filtered(db, "v2", prompt_id=None) is True
    assert await store.release_filtered(db, "v1", prompt_id=None) is False

    released = await store.get_video(db, "v2")
    assert released.state == "discovered" and released.skip_reason is None
    assert released.origins == ("channel:UC1", "manual")


async def test_a_film_released_by_a_named_prompt_is_read_by_it_and_otherwise_by_its_channels(db) -> None:
    technical = await store.create_prompt(db, name="Technical", body="Levels only.")
    await store.upsert_films(
        db,
        [Discovery(film(id_), "channel:UC1", SEEDED_PROMPT_ID, filtered_reason="a Q&A") for id_ in ("v1", "v2")],
    )

    await store.release_filtered(db, "v1", prompt_id=technical.id)
    await store.release_filtered(db, "v2", prompt_id=None)

    assert [(await store.get_video(db, v)).prompt_id for v in ("v1", "v2")] == [technical.id, SEEDED_PROMPT_ID]
