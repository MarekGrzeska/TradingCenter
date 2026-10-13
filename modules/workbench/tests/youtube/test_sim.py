"""The simulated providers: that they misbehave the way the real ones do, repeatably, and can never pass for real ones."""

from __future__ import annotations

import time
from dataclasses import replace
from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from youtube_data.analysis import Film
from youtube_data.clock import ManualClock, SimClock
from youtube_data.config import Settings
from youtube_data.providers.base import (
    Blocked,
    ChannelNotFound,
    Meter,
    NoTranscript,
    QuotaExceeded,
    ReadingUnusable,
    Transcript,
    TranscriptRequest,
)
from youtube_data.sim import scenario as scenarios
from youtube_data.sim.providers import NEUTRAL, SimAnalyser, SimListener, SimSource, SimTranscripts
from youtube_data.sim.scenario import Scenario
from youtube_data.sim.world import World

GOLD = "UCsimGoldPL0000000000000"
MARKETS = "UCsimMarketsEN0000000000"


def ask(video_id: str, *languages: str, duration: int | None = 600) -> TranscriptRequest:
    return TranscriptRequest(video_id, duration, languages, languages[0] if len(languages) == 1 else None)


def world_of(scenario: Scenario | None = None) -> tuple[World, ManualClock, Meter]:
    clock, meter = ManualClock(), Meter()
    return World(scenario or scenarios.load(), clock, meter), clock, meter


def tiny(**overrides) -> Scenario:
    """One channel and one film with captions, and whatever behaviour a test is about."""
    body = {
        "seed": 3,
        "channels": [{"channel_id": GOLD, "title": "Gold"}],
        "videos": [
            {
                "video_id": "simfilm0001",
                "channel": GOLD,
                "title": "A film",
                "captions": {"mode": "immediate", "language": "en", "text": "words"},
            }
        ],
    }
    body.update(overrides)
    return Scenario.model_validate(body)


# --- the scenario ---------------------------------------------------------------------------------------------------


def test_the_scenario_that_ships_holds_every_kind_of_transcript_the_loop_must_survive() -> None:
    default = scenarios.load()
    captions = [video.captions for video in default.videos]

    assert any(c.language == "pl" and c.text.strip() for c in captions)
    assert any(c.language == "en" and c.text.strip() for c in captions)
    assert any(c.mode == "immediate" and not c.text.strip() for c in captions), "an empty one"
    assert any("zignoruj" in c.text.lower() for c in captions), "one that talks to the model"
    assert {c.mode for c in captions} == {"immediate", "after_minutes", "never"}
    assert any(video.captions.mode == "never" and video.speech for video in default.videos), "one only a listener hears"
    assert any(video.reading == "unusable" for video in default.videos)


def test_a_scenario_that_names_what_does_not_exist_is_refused() -> None:
    with pytest.raises(ValidationError, match="not in the scenario"):
        tiny(videos=[{"video_id": "simfilm0001", "channel": "UCnobody", "title": "x"}])


# --- the source -----------------------------------------------------------------------------------------------------


async def test_films_appear_when_they_are_published_and_not_before() -> None:
    world, clock, _ = world_of()
    source = SimSource(world)
    channel = await source.resolve_channel(MARKETS)

    before = {film.video_id for film in await source.latest_videos(channel)}
    clock.advance(minutes=25)
    after = {film.video_id for film in await source.latest_videos(channel)}

    assert "simfilm0004" not in before
    assert "simfilm0004" in after


async def test_everything_a_source_says_is_marked_simulated_and_a_handle_resolves() -> None:
    world, _, _ = world_of()
    source = SimSource(world)

    channel = await source.resolve_channel("@simzloto")
    films = await source.latest_videos(channel)

    assert channel.channel_id == GOLD
    assert films and all(film.simulated for film in films)
    with pytest.raises(ChannelNotFound):
        await source.resolve_channel("@nobody-here")


async def test_a_search_finds_by_phrase_and_costs_what_the_scenario_says() -> None:
    world, clock, meter = world_of()
    clock.advance(minutes=60)

    films = await SimSource(world).search(
        "Gold outlook", language="en", published_after=None, limit=10
    )

    assert {"simfilm0001", "simfilm0003"} <= {film.video_id for film in films}
    assert meter.drain() == {("sim", "sim_units"): 101}


async def test_the_source_runs_out_of_day_and_gets_it_back_tomorrow() -> None:
    world, clock, meter = world_of(tiny(source={"daily_units": 150}))
    source = SimSource(world)
    channel = await source.resolve_channel(GOLD)  # 1

    await source.search("x", language="", published_after=None, limit=1)  # 100 + 1
    with pytest.raises(QuotaExceeded):
        await source.search("x", language="", published_after=None, limit=1)
    assert meter.drain()[("sim", "sim_units")] == 1 + 101 + 101, "a refused call is still a call"

    clock.advance(days=1)
    assert await source.latest_videos(channel) is not None


# --- the transcript provider ----------------------------------------------------------------------------------------


async def test_captions_that_arrive_hours_late_are_absent_and_charged_until_they_do() -> None:
    world, clock, meter = world_of()
    provider = SimTranscripts(world)
    clock.advance(minutes=10)

    early = await provider.fetch(ask("simfilm0003", "pl"))
    clock.advance(hours=2)
    late = await provider.fetch(ask("simfilm0003", "pl"))

    assert isinstance(early, NoTranscript) and early.charged
    assert isinstance(late, Transcript) and late.simulated and late.language == "pl"
    assert meter.drain() == {("sim", "sim_credits"): 2}


async def test_a_film_with_no_captions_is_heard_by_the_listener_and_paid_for_in_seconds_of_film() -> None:
    world, clock, meter = world_of()
    clock.advance(minutes=15)

    heard = await SimListener(world).fetch(ask("simfilm0005", "pl", duration=600))

    assert isinstance(heard, Transcript) and heard.provider == "sim_gemini" and heard.model == "sim"
    assert heard.text.startswith("[00:00] Dzień dobry, krótko o bitcoinie.")
    assert meter.drain() == {("sim_gemini", "sim_video_seconds"): 600}


async def test_captions_in_another_language_than_the_film_speaks_are_no_transcript() -> None:
    world, _, _ = world_of()

    assert isinstance(await SimTranscripts(world).fetch(ask("simfilm0001", "en")), NoTranscript)


async def test_a_listener_whose_day_is_spent_refuses_rather_than_hearing_nothing() -> None:
    world, _, _ = world_of(tiny(listening={"daily_video_seconds": 900}))
    listener = SimListener(world)

    assert isinstance(await listener.fetch(ask("simfilm0001", "en", duration=600)), Transcript)
    assert isinstance(await listener.fetch(ask("simfilm0001", "en", duration=600)), Blocked)


async def test_a_film_with_no_captions_and_one_with_only_silence_are_no_transcript() -> None:
    world, clock, _ = world_of()
    clock.advance(minutes=15)
    provider = SimTranscripts(world)

    assert isinstance(await provider.fetch(ask("simfilm0005", "pl")), NoTranscript)
    assert isinstance(await provider.fetch(ask("simfilm0008", "pl")), NoTranscript)


async def test_a_provider_that_refuses_every_request_charges_nothing_for_it() -> None:
    world, _, meter = world_of(tiny(transcripts={"block_ratio": 1.0}))

    result = await SimTranscripts(world).fetch(ask("simfilm0001", "en"))

    assert isinstance(result, Blocked)
    assert meter.drain() == {}


async def _outcomes(seed: int) -> list[str]:
    world, _, _ = world_of(tiny(seed=seed, transcripts={"block_ratio": 0.5}))
    provider = SimTranscripts(world)
    return [type(await provider.fetch(ask("simfilm0001", "en"))).__name__ for _ in range(40)]


async def test_the_same_seed_refuses_the_same_requests_and_about_the_share_asked_for() -> None:
    first, again, other = await _outcomes(3), await _outcomes(3), await _outcomes(4)

    assert first == again
    assert first != other
    assert 8 <= first.count("Blocked") <= 32


async def test_a_provider_whose_day_of_credits_is_spent_stops_answering() -> None:
    world, clock, _ = world_of(tiny(transcripts={"daily_credits": 1}))
    provider = SimTranscripts(world)

    assert isinstance(await provider.fetch(ask("simfilm0001", "en")), Transcript)
    assert isinstance(await provider.fetch(ask("simfilm0001", "en")), Blocked)
    clock.advance(days=1)
    assert isinstance(await provider.fetch(ask("simfilm0001", "en")), Transcript)


# --- the model ------------------------------------------------------------------------------------------------------

FILM = Film(video_id="simfilm0001", title="t", channel_title="c", published_on=date(2026, 9, 27), language="pl")


async def test_a_prepared_reading_is_returned_stamped_and_paid_for_in_tokens() -> None:
    world, _, _ = world_of()

    analysis = await SimAnalyser(world).read(FILM, "x" * 400, profile="market")

    assert analysis.simulated and analysis.model == "sim"
    assert analysis.reading.impact_score == 6
    assert analysis.input_tokens == 100


async def test_a_model_that_answers_badly_and_one_with_nothing_prepared() -> None:
    world, _, _ = world_of()
    analyser = SimAnalyser(world)

    with pytest.raises(ReadingUnusable):
        await analyser.read(replace(FILM, video_id="simfilm0012"), "words", profile="market")
    unknown = await analyser.read(replace(FILM, video_id="simfilm0003"), "words", profile="market")
    assert unknown.reading == NEUTRAL


# --- the clock ------------------------------------------------------------------------------------------------------


def test_a_faster_clock_runs_faster() -> None:
    clock = SimClock(speed=3600)
    started = clock.now()

    time.sleep(0.05)

    assert clock.now() - started > timedelta(minutes=1)


# --- never in a deployment ------------------------------------------------------------------------------------------


def settings(**overrides) -> Settings:
    return Settings(database_url="postgresql://localhost:5432/youtube", _env_file=None, **overrides)


@pytest.mark.parametrize(
    ("overrides", "named"),
    [
        ({"video_source": "sim", "transcript_providers": "direct", "analyser": "openai"}, "VIDEO_SOURCE"),
        (
            {"video_source": "data_api", "data_api_key": "k", "transcript_providers": "direct,sim_gemini", "analyser": "openai"},
            "TRANSCRIPT_PROVIDERS",
        ),
        ({"video_source": "data_api", "data_api_key": "k", "transcript_providers": "direct", "analyser": "sim"}, "ANALYSER"),
    ],
)
def test_a_simulated_provider_is_refused_where_the_database_is_a_deployments(overrides, named) -> None:
    deployment = {
        "database_url": "postgresql://db.example.com/youtube?sslmode=require",
        "database_user": "workbench",
        "_env_file": None,
    }

    with pytest.raises(ValidationError, match=named):
        Settings(**deployment, **overrides)


def test_the_same_choice_is_fine_on_a_workstation_and_is_the_default_there() -> None:
    local = settings()

    assert local.simulating
    assert (local.video_source, local.transcript_provider_names, local.analyser) == ("sim", ("sim", "sim_gemini"), "sim")
