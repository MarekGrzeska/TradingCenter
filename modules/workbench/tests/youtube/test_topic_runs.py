"""A topic's search leaves a report: how it ended, what the source returned and what became of it, and — when it did not go
well — why. The table's own rules (once a day, retention) are `test_store`'s; what is tested here is what the loop writes."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from youtube_data import budget, store, watchlist
from youtube_data.ingest import Ingest
from youtube_data.providers.base import (
    QuotaExceeded,
    ReadingUnusable,
    RequestInvalid,
    SourceRefused,
    SourceUnavailable,
)
from youtube_data.screening import Screening
from youtube_data.sim.providers import SimScreener, SimSource

from .harness import MARKETS, Rig
from .test_candidates import film, search, world

pytestmark = pytest.mark.db


async def runs(rig: Rig) -> list[store.TopicRun]:
    async with rig.pool.acquire() as conn:
        return list(reversed(await store.list_runs(conn)))


class Refusing(SimSource):
    """A source whose searches fail with whatever the test says — or, with no error, go through — and which remembers when
    each search was asked to start looking."""

    def __init__(self, world, error: Exception | None) -> None:
        super().__init__(world)
        self._error = error
        self.asked_from: list = []

    async def search(self, phrase, *, language, published_after, limit):
        self.asked_from.append(published_after)
        if self._error is not None:
            raise self._error
        return await super().search(phrase, language=language, published_after=published_after, limit=limit)


def failing_with(rig: Rig, error: Exception | None) -> Refusing:
    source = Refusing(rig.world, error)
    rig.providers = replace(rig.providers, source=source)
    rig.ingest = Ingest(rig.pool, rig.providers, rig.settings)
    return source


async def topic(rig: Rig):
    async with rig.pool.acquire() as conn:
        [found] = await store.list_topics(conn)
    return found


async def test_a_search_that_found_films_says_what_became_of_each(pool) -> None:
    rig = Rig(
        pool,
        world(film("new1"), film("rejected1", screening="rejected"), film("known1"), film("followed1", MARKETS)),
    )
    await watchlist.follow_channel(pool, rig.providers.source, rig.settings, MARKETS, added_by="operator")
    async with pool.acquire() as conn:
        await store.upsert_films(conn, [store.Discovery(rig.world.ref(rig.world.video("known1")), "manual", 1)])  # type: ignore[arg-type]

    await search(rig)

    [run] = await runs(rig)
    assert (run.outcome, run.phrase, run.error) == ("found", "gold", None)
    assert (run.results, run.known, run.out_of_bounds) == (4, 2, 0)
    assert (run.proposed, run.rejected, run.unscreened, run.unscreened_reason) == (1, 1, 0, None)


async def test_a_search_with_nothing_new_is_written_down_all_the_same(pool) -> None:
    rig = Rig(pool, world(film("known1"), film("short1", duration_seconds=30)))
    async with pool.acquire() as conn:
        await store.upsert_films(conn, [store.Discovery(rig.world.ref(rig.world.video("known1")), "manual", 1)])  # type: ignore[arg-type]

    await search(rig)

    [run] = await runs(rig)
    assert (run.outcome, run.results, run.known, run.out_of_bounds, run.proposed) == ("nothing_new", 2, 1, 1, 0)


@pytest.mark.parametrize(
    ("error", "said"),
    [(SourceRefused("refused search: badRequest"), "badRequest"), (QuotaExceeded("spent"), "quota")],
)
async def test_a_search_the_source_refused_says_why_and_waits_the_topics_interval_before_it_is_paid_for_again(
    pool, error: Exception, said: str
) -> None:
    rig = Rig(pool, world(film("new1")))
    source = failing_with(rig, error)

    await search(rig)
    held = await topic(rig)
    for hours in (1, 4):  # five hours in: still inside the six-hour interval
        rig.clock.advance(hours=hours)
        await rig.tick()
    asked_while_held = len(source.asked_from)
    rig.clock.advance(hours=2)
    await rig.tick()

    [run] = (await runs(rig))[:1]
    assert run.outcome == "failed" and said in (run.error or "")
    assert held.last_run_at is None
    assert held.retry_at == run.ran_at + timedelta(minutes=held.interval_minutes)
    assert (asked_while_held, len(source.asked_from)) == (1, 2)


async def test_a_search_the_source_calls_invalid_switches_the_topic_off_instead_of_paying_for_it_every_interval(pool) -> None:
    rig = Rig(pool, world(film("new1")))
    source = failing_with(rig, RequestInvalid("the YouTube Data API answered 400 for search: badRequest"))

    await search(rig)
    rig.clock.advance(days=1)
    await rig.tick()

    [run] = await runs(rig)
    off = await topic(rig)
    assert (off.active, off.retry_at, len(source.asked_from)) == (False, None, 1)
    assert run.outcome == "failed" and "badRequest" in (run.error or "") and "switched off" in (run.error or "")


async def test_a_topic_searches_only_beyond_what_the_followed_channels_need_until_midnight(pool) -> None:
    rig = Rig(pool, world(film("new1")), daily_source_units=1000)
    await watchlist.follow_channel(pool, rig.providers.source, rig.settings, MARKETS, added_by="operator")
    source = failing_with(rig, None)
    # About 150 left: enough for a search's 101, not for it and the channel's 2 units for each half hour until midnight.
    async with pool.acquire() as conn:
        await store.add_usage(conn, {("sim", "sim_units"): 850}, day=budget.utc_day(rig.clock.now()))

    await search(rig)

    [run] = await runs(rig)
    assert run.outcome == "skipped" and "followed channels" in (run.error or "")
    assert source.asked_from == []

    rig = Rig(pool, world(film("new1")))
    source = failing_with(rig, SourceUnavailable("the YouTube Data API did not answer search"))

    await search(rig)
    rig.clock.advance(minutes=30)
    await rig.tick()

    assert len(source.asked_from) == 2
    assert (await topic(rig)).retry_at is None


async def test_a_search_that_goes_through_after_a_hold_lifts_it_and_looks_from_the_last_one_that_went_through(pool) -> None:
    rig = Rig(pool, world(film("new1")))
    source = failing_with(rig, None)
    await search(rig)
    first = await topic(rig)

    failing_with(rig, SourceRefused("refused"))
    rig.clock.advance(minutes=first.interval_minutes + 1)
    await rig.tick()
    source = failing_with(rig, None)
    rig.clock.advance(minutes=first.interval_minutes + 1)
    await rig.tick()

    after = await topic(rig)
    assert source.asked_from == [first.last_run_at]
    assert after.retry_at is None and after.last_run_at is not None and after.last_run_at > first.last_run_at


async def test_a_day_that_cannot_pay_for_a_search_is_one_skipped_run_per_topic_a_day(pool) -> None:
    rig = Rig(pool, world(film("new1")), daily_source_units=50)
    await watchlist.add_topic(pool, rig.settings, "gold", added_by="operator")
    await watchlist.add_topic(pool, rig.settings, "bitcoin", added_by="operator")

    for _ in range(3):
        await rig.tick()
    rig.clock.advance(days=1)
    await rig.tick()

    skipped = await runs(rig)
    assert [(run.outcome, run.phrase) for run in skipped] == [
        ("skipped", "gold"),
        ("skipped", "bitcoin"),
        ("skipped", "gold"),
        ("skipped", "bitcoin"),
    ]
    assert "cannot pay" in (skipped[0].error or "")


class Broken:
    model = "broken"

    async def screen(self, phrase, films):
        raise ReadingUnusable("breaks the schema", tokens=50)

    async def screen_channel(self, criteria, films):
        raise AssertionError("a channel was not filtered")


class Forgetful:
    """A model that answers and leaves the films out."""

    model = "forgetful"

    async def screen(self, phrase, films):
        return Screening({}, self.model, 10, 10)

    async def screen_channel(self, criteria, films):
        raise AssertionError("a channel was not filtered")


@pytest.mark.parametrize("case", ["no_model", "day_spent", "unusable", "no_verdict"])
async def test_results_nobody_screened_say_in_the_run_why_not(pool, case: str) -> None:
    rig = Rig(pool, world(film("new1")), analyser=None if case == "no_model" else "sim")
    if case == "day_spent":
        async with pool.acquire() as conn:
            await store.add_usage(conn, {(budget.ANALYSER, budget.TOKENS): 10**9}, day=budget.utc_day(rig.clock.now()))
    if case in ("unusable", "no_verdict"):
        rig.providers = replace(rig.providers, screener=Broken() if case == "unusable" else Forgetful())  # type: ignore[arg-type]
        rig.ingest = Ingest(pool, rig.providers, rig.settings)

    await search(rig)

    [run] = await runs(rig)
    assert (run.outcome, run.unscreened, run.unscreened_reason) == ("found", 1, case)


async def test_a_screened_search_names_no_reason_for_silence(pool) -> None:
    rig = Rig(pool, world(film("new1")))
    rig.providers = replace(rig.providers, screener=SimScreener(rig.world))
    rig.ingest = Ingest(pool, rig.providers, rig.settings)

    await search(rig)

    [run] = await runs(rig)
    assert (run.proposed, run.unscreened, run.unscreened_reason) == (1, 0, None)


async def test_a_source_that_keeps_refusing_leaves_one_failed_run_a_day_until_it_says_something_else(pool) -> None:
    rig = Rig(pool, world(film("new1")))
    failing_with(rig, SourceUnavailable("the source is down"))
    await watchlist.add_topic(pool, rig.settings, "gold", added_by="operator")

    for _ in range(4):
        await rig.tick()
    failing_with(rig, SourceUnavailable("a different error"))
    await rig.tick()

    assert [(run.outcome, run.error) for run in await runs(rig)] == [
        ("failed", "the source is down"),
        ("failed", "a different error"),
    ]


async def test_a_source_out_of_quota_fails_the_topic_it_stopped_on_and_skips_the_ones_after(pool) -> None:
    rig = Rig(pool, world(film("new1")))
    failing_with(rig, QuotaExceeded("spent"))
    await watchlist.add_topic(pool, rig.settings, "gold", added_by="operator")
    await watchlist.add_topic(pool, rig.settings, "bitcoin", added_by="operator")

    await rig.tick()

    assert [(run.phrase, run.outcome) for run in await runs(rig)] == [("gold", "failed"), ("bitcoin", "skipped")]
