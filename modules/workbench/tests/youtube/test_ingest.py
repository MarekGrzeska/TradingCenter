"""The loop against the simulation: the whole road of a film, with the failures the real providers have."""

from __future__ import annotations

import pytest

from youtube_data import budget, store, watchlist
from youtube_data.providers.base import ReadingUnusable
from youtube_data.sim.scenario import Scenario

from .harness import CRYPTO, GOLD, MARKETS, Rig

pytestmark = pytest.mark.db


async def follow_all(rig: Rig, *channels: str) -> None:
    for channel in channels:
        await watchlist.follow_channel(
            rig.pool, rig.providers.source, rig.settings, channel, added_by="operator"
        )


def scenario(*videos: dict, **extra) -> Scenario:
    return Scenario.model_validate(
        {
            "seed": 1,
            "channels": [{"channel_id": GOLD, "title": "Gold"}, {"channel_id": MARKETS, "title": "Markets"}],
            "videos": [{"channel": GOLD, "title": v["video_id"], **v} for v in videos],
            **extra,
        }
    )


def spoken(video_id: str, **overrides) -> dict:
    """A ten-minute film with something said in it."""
    return {"video_id": video_id, "duration_seconds": 600, "speech": "words " * 40, **overrides}


async def test_a_film_goes_from_discovered_to_read_in_one_pass_and_is_marked_simulated_all_the_way(pool) -> None:
    rig = Rig(pool)
    await follow_all(rig, GOLD)

    await rig.tick()

    assert (await rig.states())["simfilm0001"] == "quiet"
    video = await rig.row("simfilm0001")
    assert video["simulated"] and video["origins"] == [f"channel:{GOLD}"]
    async with pool.acquire() as conn:
        assert await conn.fetchval("SELECT simulated FROM transcripts WHERE video_id = 'simfilm0001'")
        reading = await conn.fetchrow("SELECT impact_score, simulated, model FROM readings")
    assert (reading["impact_score"], reading["simulated"], reading["model"]) == (6, True, "sim")


async def test_films_that_are_not_worth_a_transcript_are_not_kept_at_all_and_a_stream_waits(pool) -> None:
    rig = Rig(pool)
    await follow_all(rig, MARKETS, CRYPTO)

    await rig.tick()
    await rig.tick()  # the source lists them again: they are not stored again

    states = await rig.states()
    assert "simfilm0009" not in states and "simfilm0010" not in states, "a Short and a five-hour marathon"
    assert states["simfilm0011"] == "discovered", "a stream still running is not asked about"
    assert await rig.used("sim", "sim_video_seconds") > 0


async def test_a_stream_is_read_once_it_has_ended(pool) -> None:
    rig = Rig(pool)
    await follow_all(rig, CRYPTO)
    await rig.tick()
    rig.clock.advance(minutes=46)

    await rig.tick()

    assert (await rig.row("simfilm0011"))["live_status"] == "none"
    assert (await rig.states())["simfilm0011"] == "quiet"


async def test_a_film_with_nothing_said_is_asked_about_four_times_at_growing_intervals_and_then_never(pool) -> None:
    rig = Rig(pool, scenario(spoken("simfilm0001", speech="   ")))
    await follow_all(rig, GOLD)

    await rig.tick()
    first = await rig.row("simfilm0001")
    assert (first["state"], first["attempts"]) == ("no_transcript", 1)

    rig.clock.advance(minutes=30)
    await rig.tick()  # not due yet: the first retry is an hour after the miss
    assert (await rig.row("simfilm0001"))["attempts"] == 1

    for _ in range(3):
        rig.clock.advance(days=2)
        await rig.tick()
    spent = await rig.used("sim", "sim_video_seconds")
    assert (await rig.row("simfilm0001"))["state"] == "gave_up"

    rig.clock.advance(days=5)
    await rig.tick()
    assert await rig.used("sim", "sim_video_seconds") == spent, "a film that was given up on is no longer asked about"
    assert spent == 4 * 600, "every ask was paid for, the misses too"


async def test_a_transcriber_that_will_not_let_us_in_spends_no_attempt_and_stops_the_pass(pool) -> None:
    rig = Rig(pool, scenario(spoken("simfilm0001"), spoken("simfilm0002"), transcriber={"block_ratio": 1.0}))
    await follow_all(rig, GOLD)

    await rig.tick()

    assert set((await rig.states()).values()) == {"discovered"}
    assert (await rig.row("simfilm0001"))["attempts"] == 0
    async with pool.acquire() as conn:
        assert (await store.provider_states(conn))["sim"].blocked
    assert await rig.used("sim", "sim_video_seconds") == 0


async def test_a_film_is_heard_in_one_pass_and_costs_its_length(pool) -> None:
    rig = Rig(pool)
    await follow_all(rig, MARKETS)

    await rig.tick()

    assert (await rig.states())["simfilm0006"] == "quiet", "an hour, heard in the same pass"
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT provider, model, automatic FROM transcripts WHERE video_id = 'simfilm0006'")
    assert dict(row) == {"provider": "sim", "model": "sim", "automatic": True}


async def test_a_film_dearer_than_what_is_left_of_the_day_waits_without_spending_an_attempt(pool) -> None:
    rig = Rig(pool, scenario(spoken("simfilm0001", duration_seconds=1200)), gemini_daily_video_seconds=900)
    await follow_all(rig, GOLD)

    await rig.tick()

    film = await rig.row("simfilm0001")
    assert (film["state"], film["attempts"]) == ("discovered", 0)
    assert await rig.used("sim", "sim_video_seconds") == 0


async def test_a_pass_does_no_more_of_a_step_than_its_limit_and_the_rest_waits(pool) -> None:
    rig = Rig(pool, scenario(spoken("simfilm0001"), spoken("simfilm0002"), spoken("simfilm0003")), transcribe_batch_limit=1)
    await follow_all(rig, GOLD)

    await rig.tick()
    assert sorted((await rig.states()).values()) == ["discovered", "discovered", "quiet"]

    await rig.tick()
    await rig.tick()
    assert set((await rig.states()).values()) == {"quiet"}


async def test_the_transcribers_day_ends_the_transcribing_and_tomorrow_resumes_it(pool) -> None:
    rig = Rig(pool, scenario(spoken("simfilm0001"), spoken("simfilm0002")), gemini_daily_video_seconds=600)
    await follow_all(rig, GOLD)

    await rig.tick()
    assert sorted((await rig.states()).values()) == ["discovered", "quiet"]
    await rig.tick()
    assert sorted((await rig.states()).values()) == ["discovered", "quiet"], "nothing more today"

    rig.clock.advance(days=1)
    await rig.tick()
    assert set((await rig.states()).values()) == {"quiet"}


async def test_the_days_tokens_stop_the_readings_and_not_the_transcripts(pool) -> None:
    rig = Rig(pool, scenario(spoken("simfilm0001"), spoken("simfilm0002")), daily_token_limit=1)
    await follow_all(rig, GOLD)

    await rig.tick()  # the first reading spends more than the whole day allows; the second waits

    assert sorted((await rig.states()).values()) == ["quiet", "transcribed"]
    rig.clock.advance(days=1)
    await rig.tick()
    assert set((await rig.states()).values()) == {"quiet"}


async def test_the_sources_day_ends_the_discovery_and_leaves_what_was_found(pool) -> None:
    rig = Rig(pool, daily_source_units=2)
    await follow_all(rig, GOLD, MARKETS)
    async with pool.acquire() as conn:
        await store.add_usage(conn, {("sim", "sim_units"): 2}, day=rig.clock.now().date())

    await rig.tick()

    assert await rig.states() == {}, "no unit left, so no channel was listed"


async def test_a_model_that_answers_badly_for_one_film_does_not_stop_the_others_and_is_given_up_on(pool) -> None:
    rig = Rig(pool, reading_max_failures=2)
    await follow_all(rig, GOLD)
    rig.clock.advance(minutes=31)

    await rig.tick()  # simfilm0012's reading breaks the schema; simfilm0001 is read all the same
    states = await rig.states()
    assert states["simfilm0001"] == "quiet" and states["simfilm0012"] == "transcribed"
    assert (await rig.row("simfilm0012"))["reading_failures"] == 1

    await rig.tick()
    await rig.tick()
    assert (await rig.row("simfilm0012"))["reading_failures"] == 2, "no longer picked up by itself"


async def test_a_model_that_cannot_be_reached_spends_none_of_a_films_attempts(pool) -> None:
    """A key, a quota or a dropped connection says nothing about the film: an hour's outage must not strand it."""

    class Down:
        model = "down"

        async def read(self, film, transcript, *, profile):
            raise ConnectionError("the provider is down")

    rig = Rig(pool, analyser=Down(), reading_max_failures=1)
    await follow_all(rig, GOLD)

    await rig.tick()
    await rig.tick()

    video = await rig.row("simfilm0001")
    assert (video["state"], video["reading_failures"]) == ("transcribed", 0)


async def test_an_answer_that_is_thrown_away_is_still_counted_against_the_days_tokens(pool) -> None:
    class Unusable:
        model = "m"

        async def read(self, film, transcript, *, profile):
            raise ReadingUnusable("breaks the schema", tokens=500)

    rig = Rig(pool, analyser=Unusable(), analyse_batch_limit=1)
    await follow_all(rig, GOLD)

    await rig.tick()

    assert await rig.used(budget.ANALYSER, budget.TOKENS) == 500


async def test_a_reading_is_stamped_by_the_loops_clock_which_the_alert_window_is_measured_on(pool) -> None:
    """A simulation running faster than the wall would otherwise let every reading fall out of the window unannounced."""
    rig = Rig(pool)
    await follow_all(rig, GOLD)

    await rig.tick()

    async with pool.acquire() as conn:
        at = await conn.fetchval("SELECT analysed_at FROM readings WHERE video_id = 'simfilm0001'")
    assert at == rig.clock.now()


async def test_without_a_model_films_are_transcribed_and_wait_unread(pool) -> None:
    rig = Rig(pool, analyser=None)
    await follow_all(rig, GOLD)

    await rig.tick()

    assert (await rig.states())["simfilm0001"] == "transcribed"
    async with pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM readings") == 0


async def test_a_film_that_a_channel_and_a_topic_both_find_is_read_once(pool) -> None:
    rig = Rig(pool)
    await follow_all(rig, GOLD)
    topic = await watchlist.add_topic(pool, rig.settings, "gold", added_by="operator", max_videos_per_run=10)

    await rig.tick()

    video = await rig.row("simfilm0001")
    assert sorted(video["origins"]) == sorted([f"channel:{GOLD}", f"topic:{topic.topic.id}"])
    async with pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM transcripts WHERE video_id = 'simfilm0001'") == 1
        assert await conn.fetchval("SELECT count(*) FROM readings WHERE video_id = 'simfilm0001'") == 1


async def test_a_topic_is_searched_when_it_is_due_and_not_before_and_pays_for_the_search(pool) -> None:
    rig = Rig(pool)
    await watchlist.add_topic(pool, rig.settings, "fed", added_by="operator", interval_minutes=60)
    rig.clock.advance(minutes=20)

    await rig.tick()
    searched = await rig.used("sim", "sim_units")
    assert searched == rig.providers.source.search_cost

    rig.clock.advance(minutes=30)
    await rig.tick()
    assert await rig.used("sim", "sim_units") == searched, "not due for another half hour"

    rig.clock.advance(minutes=31)
    await rig.tick()
    assert await rig.used("sim", "sim_units") == 2 * searched


async def test_a_step_that_breaks_does_not_stop_the_ones_after_it_but_the_pass_is_a_failed_one(pool) -> None:
    rig = Rig(pool)
    await follow_all(rig, GOLD)
    await rig.tick()  # everything already read
    async with pool.acquire() as conn:
        await store.upsert_films(
            conn,
            [store.Discovery(_ref("late01"), "manual", "market", "never")],
        )
    real = rig.providers.source.latest_videos

    async def broken(channel):
        raise RuntimeError("a bug, not a source that failed")

    rig.providers.source.latest_videos = broken  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        await rig.tick()
    rig.providers.source.latest_videos = real  # type: ignore[method-assign]

    # The transcription that comes after discovery still ran, and the failed pass is what the heartbeat is denied.
    assert (await rig.row("late01"))["attempts"] == 1


def _ref(video_id: str):
    from datetime import UTC, datetime

    from youtube_data.providers.base import VideoRef

    return VideoRef(
        video_id=video_id,
        channel_id=GOLD,
        channel_title="Gold",
        title="a late film",
        published_at=datetime(2026, 9, 27, 7, 0, tzinfo=UTC),
    )


async def _beat_after(rig: Rig, *, breaks: bool) -> bool:
    """Whether a started loop reported a completed pass within a moment — the age `/health` publishes."""
    import asyncio

    from tc_runtime.liveness import LoopHeartbeat

    heartbeat = LoopHeartbeat("ingest", expected_seconds=1800)
    if breaks:

        async def broken(channel):
            raise RuntimeError("a bug, not a source that failed")

        rig.providers.source.latest_videos = broken  # type: ignore[method-assign]
    rig.ingest = type(rig.ingest)(rig.pool, rig.providers, rig.settings, heartbeat=heartbeat)
    await follow_all(rig, GOLD)

    await rig.ingest.start()
    try:
        for _ in range(40):
            if heartbeat.has_run:
                break
            await asyncio.sleep(0.05)
    finally:
        await rig.ingest.stop()
    return heartbeat.has_run


async def test_the_loop_reports_a_pass_only_when_it_completed_one(pool) -> None:
    assert await _beat_after(Rig(pool), breaks=False) is True
    assert await _beat_after(Rig(pool), breaks=True) is False


# --- a film named by hand is not left to the queue ---------------------------------------------------------------------


async def test_a_film_named_by_hand_is_read_at_once_and_the_rest_of_the_queue_is_left_alone(pool) -> None:
    rig = Rig(pool, scenario(spoken("simfilm0001"), spoken("simfilm0002")))
    for wanted in ("simfilm0001", "simfilm0002"):
        await watchlist.analyse_film(pool, rig.providers, rig.settings, wanted)

    await rig.ingest.process_now("simfilm0001")

    assert await rig.states() == {"simfilm0001": "quiet", "simfilm0002": "discovered"}


async def test_naming_a_film_again_asks_for_its_words_now_and_not_at_the_date_its_last_miss_set(pool) -> None:
    rig = Rig(pool, scenario(spoken("simfilm0001", speech="")))
    await watchlist.analyse_film(pool, rig.providers, rig.settings, "simfilm0001")
    await rig.ingest.process_now("simfilm0001")  # nothing heard: a miss, asked again in an hour
    assert (await rig.row("simfilm0001"))["state"] == "no_transcript"

    film = rig.world.video("simfilm0001")
    assert film is not None
    film.speech = "words " * 40
    rig.clock.advance(minutes=35)
    again = await watchlist.analyse_film(pool, rig.providers, rig.settings, "simfilm0001")
    await rig.ingest.process_now("simfilm0001")

    assert again.created is False and again.process
    assert (await rig.row("simfilm0001"))["state"] == "quiet", "not due for another 25 minutes, and asked all the same"


async def test_a_film_that_is_already_read_is_not_processed_again(pool) -> None:
    rig = Rig(pool, scenario(spoken("simfilm0001")))
    await watchlist.analyse_film(pool, rig.providers, rig.settings, "simfilm0001")
    await rig.ingest.process_now("simfilm0001")
    spent = await rig.used("sim", "sim_video_seconds")

    again = await watchlist.analyse_film(pool, rig.providers, rig.settings, "simfilm0001")
    await rig.ingest.process_now("simfilm0001")

    assert not again.process
    assert await rig.used("sim", "sim_video_seconds") == spent


async def test_a_pass_and_a_film_named_by_hand_do_not_spend_the_same_day_twice(pool) -> None:
    import asyncio

    rig = Rig(pool, scenario(spoken("simfilm0001")))
    await watchlist.analyse_film(pool, rig.providers, rig.settings, "simfilm0001")

    await asyncio.gather(rig.tick(), rig.ingest.process_now("simfilm0001"))

    assert await rig.used("sim", "sim_video_seconds") == 600, "one film, asked about once"


async def test_a_crowded_transcriber_rests_minutes_and_is_asked_again(pool) -> None:
    """Nine films once waited six hours behind one 503: the transcriber is back as soon as the model is."""
    rig = Rig(pool, scenario(spoken("simfilm0001")), transcriber_cooldown_minutes=15)
    rig.world.scenario.transcriber.block_ratio = 1.0
    await follow_all(rig, GOLD)

    await rig.tick()
    assert (await rig.states())["simfilm0001"] == "discovered", "refused: the model is crowded"

    rig.world.scenario.transcriber.block_ratio = 0.0
    rig.clock.advance(minutes=10)
    await rig.tick()
    assert (await rig.states())["simfilm0001"] == "discovered", "still resting"

    rig.clock.advance(minutes=10)
    await rig.tick()
    assert (await rig.states())["simfilm0001"] == "quiet", "twenty minutes on, it is asked again and hears it"


async def test_a_short_under_three_minutes_is_not_kept(pool) -> None:
    rig = Rig(pool, scenario(spoken("simfilm0001", duration_seconds=150)))
    await follow_all(rig, GOLD)

    await rig.tick()

    assert await rig.states() == {}


async def test_naming_a_short_by_hand_is_refused_with_the_reason_and_stores_nothing(pool) -> None:
    rig = Rig(pool, scenario(spoken("simfilm0001", duration_seconds=150)))

    with pytest.raises(watchlist.WatchlistRefused, match="floor"):
        await watchlist.analyse_film(pool, rig.providers, rig.settings, "simfilm0001")

    assert await rig.states() == {}
