"""A channel's filter in the loop: what is put to the model, what is stored for each answer, and what waits. The
screening's wording has its own tests in `test_screening`; the routes' in `test_api`."""

from __future__ import annotations

from dataclasses import replace

import pytest

from youtube_data import budget, store, watchlist
from youtube_data.ingest import JUDGE_MAX_FAILURES, Ingest
from youtube_data.providers.base import ReadingUnusable
from youtube_data.screening import Screening
from youtube_data.sim.providers import SimAnalyser, SimScreener
from youtube_data.sim.scenario import Scenario

from .harness import GOLD, Rig

pytestmark = pytest.mark.db

FILTER = "only macro analyses"


def world(*videos: dict) -> Scenario:
    return Scenario.model_validate(
        {
            "seed": 1,
            "channels": [{"channel_id": GOLD, "title": "Gold"}],
            "videos": [
                {"channel": GOLD, "duration_seconds": 600, "speech": "words " * 40, "title": v["video_id"], **v}
                for v in videos
            ],
        }
    )


class Recording:
    """The simulated screener, remembering which films each channel call was given."""

    model = "recording"

    def __init__(self, inner: SimScreener, *, answering: set[str] | None = None) -> None:
        self._inner = inner
        self._answering = answering
        self.asked: list[tuple[str, list[str]]] = []

    async def screen(self, phrase, films):
        return await self._inner.screen(phrase, films)

    async def screen_channel(self, criteria, films):
        self.asked.append((criteria, [film.video_id for film in films]))
        answered = await self._inner.screen_channel(criteria, films)
        if self._answering is None:
            return answered
        kept = {id_: v for id_, v in answered.verdicts.items() if id_ in self._answering}
        return Screening(kept, answered.model, answered.input_tokens, answered.output_tokens)


class Broken:
    model = "broken"

    async def screen(self, phrase, films):
        raise AssertionError("a topic was not searched")

    async def screen_channel(self, criteria, films):
        raise ReadingUnusable("breaks the schema", tokens=50)


def using(rig: Rig, screener) -> None:
    rig.providers = replace(rig.providers, screener=screener)
    rig.ingest = Ingest(rig.pool, rig.providers, rig.settings)


async def follow(rig: Rig, filter: str | None = FILTER) -> None:
    await watchlist.follow_channel(rig.pool, rig.providers.source, rig.settings, GOLD, added_by="operator", filter=filter)


async def test_a_film_that_passes_goes_on_and_one_that_does_not_is_kept_unread_with_the_reason(pool) -> None:
    rig = Rig(pool, world({"video_id": "pass1"}, {"video_id": "turned1", "screening": "rejected"}))
    await follow(rig)

    await rig.tick()

    assert await rig.states() == {"pass1": "quiet", "turned1": "filtered_out"}
    assert (await rig.row("turned1"))["skip_reason"]
    assert await rig.used("sim", "sim_video_seconds") == 600
    async with pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM transcripts WHERE video_id = 'turned1'") == 0


async def test_a_film_is_put_to_the_model_once_however_often_its_channel_lists_it(pool) -> None:
    rig = Rig(pool, world({"video_id": "pass1"}, {"video_id": "turned1", "screening": "rejected"}))
    spy = Recording(SimScreener(rig.world))
    using(rig, spy)
    await follow(rig)

    await rig.tick()
    spent = await rig.used(budget.ANALYSER, budget.TOKENS)
    await rig.tick()

    assert [(criteria, sorted(ids)) for criteria, ids in spy.asked] == [(FILTER, ["pass1", "turned1"])]
    assert await rig.used(budget.ANALYSER, budget.TOKENS) == spent


async def test_a_channel_without_a_filter_is_never_put_to_the_model(pool) -> None:
    rig = Rig(pool, world({"video_id": "pass1"}, {"video_id": "turned1", "screening": "rejected"}))
    spy = Recording(SimScreener(rig.world))
    using(rig, spy)
    await follow(rig, filter=None)

    await rig.tick()

    assert spy.asked == []
    assert await rig.states() == {"pass1": "quiet", "turned1": "quiet"}


async def test_only_films_the_archive_has_not_seen_and_are_worth_a_transcript_are_put_to_the_model(pool) -> None:
    rig = Rig(pool, world({"video_id": "known1"}, {"video_id": "short1", "duration_seconds": 60}, {"video_id": "new1"}))
    async with pool.acquire() as conn:
        await store.upsert_films(conn, [store.Discovery(rig.world.ref(rig.world.video("known1")), "manual", 1)])  # type: ignore[arg-type]
    spy = Recording(SimScreener(rig.world))
    using(rig, spy)
    await follow(rig)

    await rig.tick()

    assert spy.asked == [(FILTER, ["new1"])]
    assert set(await rig.states()) == {"known1", "new1"}


@pytest.mark.parametrize("case", ["no model", "no tokens left", "unusable answer"])
async def test_a_film_nobody_could_judge_is_neither_stored_nor_transcribed_and_is_judged_when_somebody_can(
    pool, case: str
) -> None:
    rig = Rig(pool, world({"video_id": "pass1"}), analyser=None if case == "no model" else "sim")
    if case == "no tokens left":
        async with pool.acquire() as conn:
            await store.add_usage(conn, {(budget.ANALYSER, budget.TOKENS): 10**9}, day=budget.utc_day(rig.clock.now()))
    if case == "unusable answer":
        using(rig, Broken())
    await follow(rig)

    await rig.tick()

    assert await rig.states() == {}
    assert await rig.used("sim", "sim_video_seconds") == 0
    if case == "unusable answer":
        assert await rig.used(budget.ANALYSER, budget.TOKENS) == 50

    if case == "no tokens left":
        rig.clock.advance(days=1)
    rig.providers = replace(rig.providers, analyser=SimAnalyser(rig.world))
    using(rig, SimScreener(rig.world))
    await rig.tick()

    assert set(await rig.states()) == {"pass1"}


async def test_a_film_the_model_gave_no_verdict_for_waits_while_the_others_are_stored(pool) -> None:
    rig = Rig(pool, world({"video_id": "pass1"}, {"video_id": "silent1"}))
    using(rig, Recording(SimScreener(rig.world), answering={"pass1"}))
    await follow(rig)

    await rig.tick()

    assert set(await rig.states()) == {"pass1"}


async def test_judging_a_film_spends_tokens_and_no_transcript(pool) -> None:
    rig = Rig(pool, world({"video_id": "turned1", "screening": "rejected"}))
    await follow(rig)

    await rig.tick()

    assert await rig.used(budget.ANALYSER, budget.TOKENS) > 0
    assert await rig.used("sim", "sim_video_seconds") == 0


async def test_taking_the_filter_off_leaves_what_it_turned_away_and_passes_what_comes_after(pool) -> None:
    rig = Rig(
        pool,
        world(
            {"video_id": "old1", "screening": "rejected"},
            {"video_id": "late1", "screening": "rejected", "published_after_start_minutes": 120},
        ),
    )
    await follow(rig)
    await rig.tick()
    assert await rig.states() == {"old1": "filtered_out"}

    async with pool.acquire() as conn:
        await store.update_channel(conn, GOLD, filter=None)
    rig.clock.advance(hours=3)
    await rig.tick()

    assert await rig.states() == {"old1": "filtered_out", "late1": "quiet"}


async def test_a_film_the_filter_turned_away_is_transcribed_and_read_once_somebody_names_it(pool) -> None:
    rig = Rig(pool, world({"video_id": "simturned01", "screening": "rejected"}))
    await follow(rig)
    await rig.tick()

    queued = await watchlist.analyse_film(pool, rig.providers, rig.settings, "simturned01")
    await rig.ingest.process_now(queued.video_id)

    assert (queued.created, queued.process) == (False, True)
    assert await rig.states() == {"simturned01": "quiet"}
    assert await rig.used("sim", "sim_video_seconds") == 600


class Unreachable:
    model = "unreachable"

    async def screen(self, phrase, films):
        raise AssertionError("a topic was not searched")

    async def screen_channel(self, criteria, films):
        raise ConnectionError("the provider is down")


async def test_a_film_the_model_keeps_answering_nothing_about_is_kept_filtered_out_saying_so(pool) -> None:
    rig = Rig(pool, world({"video_id": "silent1"}))
    using(rig, Recording(SimScreener(rig.world), answering=set()))
    await follow(rig)

    for _ in range(JUDGE_MAX_FAILURES - 1):
        await rig.tick()
    assert await rig.states() == {}
    await rig.tick()

    assert await rig.states() == {"silent1": "filtered_out"}
    assert "nie udało się ocenić" in (await rig.row("silent1"))["skip_reason"]


async def test_a_model_nobody_could_reach_spends_none_of_a_films_answers(pool) -> None:
    rig = Rig(pool, world({"video_id": "pass1"}))
    using(rig, Unreachable())
    await follow(rig)

    for _ in range(JUDGE_MAX_FAILURES + 1):
        await rig.tick()

    assert await rig.states() == {}


async def test_a_stream_still_running_waits_unjudged_and_is_judged_once_it_has_ended(pool) -> None:
    rig = Rig(pool, world({"video_id": "live1", "live_until_minutes": 30, "screening": "rejected"}))
    spy = Recording(SimScreener(rig.world))
    using(rig, spy)
    await follow(rig)

    await rig.tick()
    assert (spy.asked, await rig.states()) == ([], {})

    rig.clock.advance(hours=1)
    await rig.tick()

    assert spy.asked == [(FILTER, ["live1"])]
    assert (await rig.row("live1"))["live_status"] == "none"
    assert await rig.states() == {"live1": "filtered_out"}
