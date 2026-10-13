"""The queries the loop stands on. What is checked is the behaviour the loop needs from them, and one cost rule: a film seen
again writes nothing."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from youtube_data import store
from youtube_data.analysis import Reading
from youtube_data.providers.base import ChannelInfo, VideoRef
from youtube_data.store import Discovery, ProviderState

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
    return Discovery(film(video_id, **overrides), origin, "market", "threshold")


async def test_following_a_channel_twice_keeps_what_the_operator_set(db) -> None:
    info = ChannelInfo(channel_id="UC1", title="A Channel")
    first = await store.add_channel(db, info, language="pl", profile="market", alert_rule="always", added_by="operator")

    again = await store.add_channel(db, info, language="", profile="market", alert_rule="never", added_by="agent")

    assert again == first
    assert again.alert_rule == "always" and again.added_by == "operator"


async def test_pausing_a_channel_is_not_removing_it(db) -> None:
    info = ChannelInfo(channel_id="UC1", title="A Channel")
    await store.add_channel(db, info, language="", profile="market", alert_rule="threshold", added_by="operator")

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
    await db.execute("INSERT INTO videos (video_id, title, published_at, origins, state, skip_reason) "
                     "VALUES ('old', 'x', now(), ARRAY['manual'], 'skipped', 'older version')")

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


async def test_a_reading_overwrites_the_last_one_and_names_its_instruments_in_lower_case(db) -> None:
    await store.upsert_films(db, [discovery()])
    reading = Reading.model_validate(
        {
            "summary_pl": "x",
            "key_points": [],
            "instruments": [{"name": "Gold", "epic": "XAUUSD", "sentiment": "bullish", "conviction": 3, "horizon": "swing"}],
            "predictions": [],
            "topics": [],
            "impact_score": 4,
        }
    )

    await store.save_reading(db, "v1", profile="market", reading=reading, model="m1", simulated=False)
    await store.save_reading(
        db, "v1", profile="market", reading=reading.model_copy(update={"impact_score": 8}), model="m2", simulated=True
    )

    rows = await db.fetch("SELECT impact_score, model, instruments, simulated FROM readings")
    assert len(rows) == 1
    assert (rows[0]["impact_score"], rows[0]["model"], rows[0]["simulated"]) == (8, "m2", True)
    assert rows[0]["instruments"] == ["gold", "xauusd"]


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
