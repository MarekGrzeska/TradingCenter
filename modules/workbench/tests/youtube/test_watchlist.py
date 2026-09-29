"""What the operator and the agent may add, and what is refused before anything is written."""

from __future__ import annotations

import pytest

from youtube_data import store, watchlist
from youtube_data.watchlist import WatchlistRefused

from .harness import GOLD, Rig

pytestmark = pytest.mark.db


async def follow(rig: Rig, reference: str, **kwargs):
    return await watchlist.follow_channel(
        rig.pool, rig.providers.source, rig.settings, reference, added_by="operator", **kwargs
    )


async def test_a_channel_is_followed_by_its_handle_and_by_any_other_spelling_of_it_once(pool) -> None:
    rig = Rig(pool)

    first = await follow(rig, "@simzloto")
    again = await follow(rig, f"https://www.youtube.com/channel/{GOLD}")

    assert first.created and first.channel.channel_id == GOLD
    assert not again.created and again.channel == first.channel
    async with pool.acquire() as conn:
        assert await store.count_channels(conn) == 1


async def test_a_reference_that_names_no_channel_is_refused_and_writes_nothing(pool) -> None:
    rig = Rig(pool)

    with pytest.raises(WatchlistRefused, match="no channel"):
        await follow(rig, "@nobody-here")
    async with pool.acquire() as conn:
        assert await store.count_channels(conn) == 0


async def test_the_ceiling_refuses_the_channel_that_would_pass_it_and_points_at_the_operator(pool) -> None:
    rig = Rig(pool, max_channels=1)
    await follow(rig, "@simzloto")

    with pytest.raises(WatchlistRefused, match="ceiling.*operator"):
        await follow(rig, "@simmarkets")
    # Already following is not adding, so the ceiling does not apply to it.
    assert not (await follow(rig, "@simzloto")).created


async def test_a_topic_added_by_phrase_alone_gets_the_settings_limits_and_says_so(pool) -> None:
    rig = Rig(pool)

    added = await watchlist.add_topic(pool, rig.settings, "  Gold   outlook ", added_by="agent")

    assert added.created and added.topic.phrase == "Gold outlook"
    assert added.topic.interval_minutes == rig.settings.topic_default_interval_minutes
    assert added.defaults_applied == ("interval_minutes", "max_videos_per_run")
    again = await watchlist.add_topic(pool, rig.settings, "GOLD OUTLOOK", added_by="operator")
    assert not again.created and again.topic.id == added.topic.id


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"phrase": "  "}, "phrase"),
        ({"phrase": "gold", "interval_minutes": 5}, "at most every"),
        ({"phrase": "gold", "max_videos_per_run": 99}, "between 1 and"),
        ({"phrase": "gold", "alert_rule": "sometimes"}, "alert_rule"),
    ],
)
async def test_a_topic_without_sensible_limits_is_refused(pool, kwargs, match) -> None:
    with pytest.raises(WatchlistRefused, match=match):
        await watchlist.add_topic(pool, Rig(pool).settings, added_by="agent", **kwargs)


async def test_the_topic_ceiling_is_the_same_for_the_agent_as_for_the_screen(pool) -> None:
    rig = Rig(pool, max_topics=1)
    await watchlist.add_topic(pool, rig.settings, "gold", added_by="operator")

    with pytest.raises(WatchlistRefused, match="ceiling"):
        await watchlist.add_topic(pool, rig.settings, "bitcoin", added_by="agent")


async def test_a_film_named_by_hand_is_queued_once_and_costs_what_asking_costs(pool) -> None:
    rig = Rig(pool)
    rig.clock.advance(minutes=60)

    queued = await watchlist.analyse_film(pool, rig.providers, rig.settings, "https://youtu.be/simfilm0004")
    again = await watchlist.analyse_film(pool, rig.providers, rig.settings, "simfilm0004")

    assert queued.created and not again.created
    video = await rig.row("simfilm0004")
    assert video["origins"] == ["manual"] and video["state"] == "discovered"
    assert await rig.used("sim", "sim_units") == 1


async def test_a_film_that_is_not_one_and_a_film_that_does_not_exist_are_refused(pool) -> None:
    rig = Rig(pool)

    with pytest.raises(WatchlistRefused, match="not a YouTube film"):
        await watchlist.analyse_film(pool, rig.providers, rig.settings, "https://example.com/x")
    with pytest.raises(WatchlistRefused, match="knows no film"):
        await watchlist.analyse_film(pool, rig.providers, rig.settings, "zzzzzzzzzzz")


async def test_a_film_by_hand_is_refused_once_the_sources_day_is_spent(pool) -> None:
    rig = Rig(pool, daily_source_units=1)
    async with pool.acquire() as conn:
        await store.add_usage(conn, {("sim", "sim_units"): 1}, day=rig.clock.now().date())

    with pytest.raises(WatchlistRefused, match="day is spent"):
        await watchlist.analyse_film(pool, rig.providers, rig.settings, "simfilm0001")
