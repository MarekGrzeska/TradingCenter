"""A topic's search leaves a report: how it ended, what the source returned and what became of it, and — when it did not go
well — why. The table's own rules (once a day, retention) are `test_store`'s; what is tested here is what the loop writes."""

from __future__ import annotations

from dataclasses import replace

import pytest

from youtube_data import budget, store, watchlist
from youtube_data.ingest import Ingest
from youtube_data.providers.base import QuotaExceeded, ReadingUnusable, SourceUnavailable
from youtube_data.screening import Screening
from youtube_data.sim.providers import SimScreener, SimSource

from .harness import MARKETS, Rig
from .test_candidates import film, search, world

pytestmark = pytest.mark.db


async def runs(rig: Rig) -> list[store.TopicRun]:
    async with rig.pool.acquire() as conn:
        return list(reversed(await store.list_runs(conn)))


class Refusing(SimSource):
    """A source whose searches fail with whatever the test says."""

    def __init__(self, world, error: Exception) -> None:
        super().__init__(world)
        self._error = error

    async def search(self, *args, **kwargs):
        raise self._error


def failing_with(rig: Rig, error: Exception) -> None:
    rig.providers = replace(rig.providers, source=Refusing(rig.world, error))
    rig.ingest = Ingest(rig.pool, rig.providers, rig.settings)


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
    [(SourceUnavailable("the source is down"), "the source is down"), (QuotaExceeded("spent"), "quota")],
)
async def test_a_search_the_source_refused_says_why_and_is_tried_again_next_pass(pool, error: Exception, said: str) -> None:
    rig = Rig(pool, world(film("new1")))
    failing_with(rig, error)

    await search(rig)

    [run] = await runs(rig)
    assert run.outcome == "failed" and said in (run.error or "")
    async with pool.acquire() as conn:
        assert [topic.last_run_at for topic in await store.list_topics(conn)] == [None]


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
