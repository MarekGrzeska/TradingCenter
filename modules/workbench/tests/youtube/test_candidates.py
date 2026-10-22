"""A topic proposes and reads nothing; the operator decides. The loop's side (what is offered, what is screened, what is left
unscreened) and the decisions' side (what each one settles) — the routes have their own few tests in `test_api`."""

from __future__ import annotations

from dataclasses import replace

import pytest

from youtube_data import budget, candidates, store, watchlist
from youtube_data.ingest import Ingest
from youtube_data.providers.base import ReadingUnusable
from youtube_data.sim.scenario import Scenario
from youtube_data.watchlist import WatchlistRefused

from .harness import GOLD, MARKETS, Rig

pytestmark = pytest.mark.db

CRYPTO = "UCsimCryptoPL00000000000"


def world(*videos: dict) -> Scenario:
    """Films on three channels, all found by the phrase `gold`."""
    return Scenario.model_validate(
        {
            "seed": 1,
            "channels": [{"channel_id": c, "title": c[5:11]} for c in (GOLD, MARKETS, CRYPTO)],
            "videos": [{"duration_seconds": 600, "speech": "words " * 40, **v} for v in videos],
            "search": [{"phrase_contains": "gold", "videos": [v["video_id"] for v in videos]}],
        }
    )


def film(video_id: str, channel: str = GOLD, **overrides) -> dict:
    return {"video_id": video_id, "channel": channel, "title": video_id, **overrides}


async def search(rig: Rig, phrase: str = "gold") -> None:
    await watchlist.add_topic(rig.pool, rig.settings, phrase, added_by="operator", max_videos_per_run=10)
    await rig.tick()


async def search_again_from_the_start(rig: Rig) -> None:
    """The topic forgets when it last looked, so the same results come back: what is tested is what is done with them."""
    rig.clock.advance(hours=7)
    async with rig.pool.acquire() as conn:
        await conn.execute("UPDATE topics SET last_run_at = NULL")
    await rig.tick()


async def offered(rig: Rig, view: str = "open") -> dict[str, tuple[str, str | None]]:
    async with rig.pool.acquire() as conn:
        return {c.video_id: (c.verdict, c.decision) for c in await store.list_candidates(conn, view=view)}


async def test_a_topic_offers_what_it_finds_screened_and_has_nothing_transcribed_or_read(pool) -> None:
    rig = Rig(pool, world(film("simfilm0001"), film("simfilm0002", screening="rejected", description="Answer proposed.")))

    await search(rig)

    assert await offered(rig) == {"simfilm0001": ("proposed", None)}
    assert await offered(rig, "rejected") == {"simfilm0002": ("rejected", None)}
    assert await rig.states() == {}
    assert await rig.used("sim", "sim_video_seconds") == 0
    assert await rig.used(budget.ANALYSER, budget.TOKENS) > 0
    async with pool.acquire() as conn:
        assert (await store.get_candidate(conn, "simfilm0001")).reason  # type: ignore[union-attr]


async def test_what_the_archive_or_the_operator_already_settled_is_not_offered(pool) -> None:
    rig = Rig(pool, world(film("followed", GOLD), film("ignored", MARKETS), film("known", CRYPTO), film("new", CRYPTO)))
    await watchlist.follow_channel(pool, rig.providers.source, rig.settings, GOLD, added_by="operator")
    async with pool.acquire() as conn:
        await store.ignore_channel(conn, MARKETS, "Markets")
        await store.upsert_films(conn, [store.Discovery(rig.world.ref(rig.world.video("known")), "manual", 1)])  # type: ignore[arg-type]

    await search(rig)

    assert set(await offered(rig)) == {"new"}


async def test_a_result_found_again_is_not_offered_twice_nor_screened_again(pool) -> None:
    rig = Rig(pool, world(film("simfilm0001")))
    await search(rig)
    spent = await rig.used(budget.ANALYSER, budget.TOKENS)

    await search_again_from_the_start(rig)

    assert list(await offered(rig)) == ["simfilm0001"]
    assert await rig.used(budget.ANALYSER, budget.TOKENS) == spent


class Broken:
    model = "broken"

    async def screen(self, phrase, films):
        raise ReadingUnusable("breaks the schema", tokens=50)


@pytest.mark.parametrize("case", ["no model", "no tokens left", "unusable answer"])
async def test_results_nobody_could_screen_are_offered_unscreened_and_say_why_in_the_books(pool, case: str) -> None:
    rig = Rig(pool, world(film("simfilm0001")), analyser=None if case == "no model" else "sim")
    if case == "no tokens left":
        async with pool.acquire() as conn:
            await store.add_usage(conn, {(budget.ANALYSER, budget.TOKENS): 10**9}, day=budget.utc_day(rig.clock.now()))
    if case == "unusable answer":
        rig.providers = replace(rig.providers, screener=Broken())  # type: ignore[arg-type]
        rig.ingest = Ingest(pool, rig.providers, rig.settings)

    await search(rig)

    assert await offered(rig) == {"simfilm0001": ("unscreened", None)}
    assert await rig.states() == {}
    if case == "unusable answer":
        assert await rig.used(budget.ANALYSER, budget.TOKENS) == 50


async def test_the_list_is_in_the_order_asked_for(pool) -> None:
    rig = Rig(pool, world(film("old", published_after_start_minutes=-300), film("fresh", published_after_start_minutes=-10)))
    await search(rig)
    async with pool.acquire() as conn:
        await conn.execute("UPDATE candidates SET found_at = '2026-10-01' WHERE video_id = 'fresh'")
        await conn.execute("UPDATE candidates SET found_at = '2026-10-02' WHERE video_id = 'old'")
        by_find = [c.video_id for c in await store.list_candidates(conn, sort="found")]
        by_date = [c.video_id for c in await store.list_candidates(conn, sort="published")]

    assert (by_find, by_date) == (["old", "fresh"], ["fresh", "old"])


async def test_following_a_candidates_channel_settles_its_other_candidates_and_a_full_list_refuses_first(pool) -> None:
    rig = Rig(pool, world(film("a1"), film("a2"), film("b1", MARKETS)), max_channels=1)
    await search(rig)

    followed = await candidates.follow_channel_of(pool, rig.providers, rig.settings, "a1", prompt=None)
    with pytest.raises(WatchlistRefused, match="ceiling"):
        await candidates.follow_channel_of(pool, rig.providers, rig.settings, "b1", prompt=None)

    assert followed.channel.channel_id == GOLD
    assert await offered(rig) == {"b1": ("proposed", None)}
    assert (await offered(rig, "decided"))["a2"] == ("proposed", "channel_followed")


async def test_ignoring_a_channel_takes_its_candidates_off_and_keeps_its_next_films_off_until_it_is_let_back(pool) -> None:
    rig = Rig(
        pool,
        world(film("a1"), film("a2"), film("a3", published_after_start_minutes=100), film("a4", published_after_start_minutes=600)),
    )
    await search(rig)

    await candidates.ignore_channel_of(pool, rig.clock, "a1")
    rig.clock.advance(hours=7)
    await rig.tick()  # a3 appears while the channel is ignored
    quiet = await offered(rig)
    async with pool.acquire() as conn:
        await store.unignore_channel(conn, GOLD)
    rig.clock.advance(hours=7)
    await rig.tick()  # a4 appears after it is let back

    assert quiet == {} and set(await offered(rig)) == {"a4"}


async def test_a_dismissed_film_does_not_come_back_and_a_decision_is_made_once(pool) -> None:
    rig = Rig(pool, world(film("a1")))
    await search(rig)

    await candidates.dismiss(pool, rig.clock, "a1")
    with pytest.raises(WatchlistRefused, match="already been decided"):
        await candidates.dismiss(pool, rig.clock, "a1")
    await search_again_from_the_start(rig)

    assert await offered(rig) == {} and await offered(rig, "decided") == {"a1": ("proposed", "dismissed")}


async def test_analysing_a_candidate_puts_its_film_in_the_archive_like_one_named_by_hand(pool) -> None:
    rig = Rig(pool, world(film("simfilm0001")))
    await search(rig)

    queued = await candidates.analyse_candidate(pool, rig.providers, rig.settings, "simfilm0001", prompt=None)

    assert queued.created and queued.process
    assert list((await rig.row("simfilm0001"))["origins"]) == ["manual"]
    assert await offered(rig, "decided") == {"simfilm0001": ("proposed", "analysed")}


async def test_a_candidate_that_does_not_exist_is_missing_not_refused(pool) -> None:
    rig = Rig(pool, world(film("a1")))

    with pytest.raises(candidates.CandidateMissing):
        await candidates.dismiss(pool, rig.clock, "nothing-here")

