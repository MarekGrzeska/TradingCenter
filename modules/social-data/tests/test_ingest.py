"""The collection pass: which dates it asks for, what it writes, and what a source that will not
answer does — and does not do — to what is already there."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta

import pytest
from builders import TRUTH_SOCIAL, raw_post
from fakes import FakeSource
from tc_runtime.liveness import LoopHeartbeat

from social_data import store
from social_data.ingest import Ingest, dates_touched

pytestmark = pytest.mark.db

# Late enough that a 24-hour window reaches back into the previous calendar date.
JUST_BEFORE_MIDNIGHT = datetime(2026, 8, 31, 23, 30, tzinfo=UTC)


def at(moment: datetime):
    return lambda: moment


def test_a_window_names_every_date_it_touches():
    start = datetime(2026, 8, 30, 23, 50, tzinfo=UTC)
    assert dates_touched(start, start + timedelta(hours=1)) == [date(2026, 8, 30), date(2026, 8, 31)]
    assert dates_touched(start, start + timedelta(minutes=5)) == [date(2026, 8, 30)]


async def test_a_pass_asks_the_source_for_both_dates_a_window_crosses(pool):
    source = FakeSource(name=TRUTH_SOCIAL)
    ingest = Ingest(pool, [source], interval_seconds=60, window_hours=24, clock=at(JUST_BEFORE_MIDNIGHT))

    await ingest.collect(source)

    assert source.asked == [date(2026, 8, 30), date(2026, 8, 31)]


async def test_a_post_published_before_midnight_is_collected(pool):
    late = raw_post("late", published_at=datetime(2026, 8, 30, 23, 50, tzinfo=UTC))
    source = FakeSource(by_day={date(2026, 8, 30): [late], date(2026, 8, 31): []})
    ingest = Ingest(pool, [source], interval_seconds=60, window_hours=24, clock=at(JUST_BEFORE_MIDNIGHT))

    result = await ingest.collect(source)

    assert (result.fetched, result.inserted) == (1, 1)
    async with pool.acquire() as conn:
        assert await store.post_by_external_id(conn, TRUTH_SOCIAL, "late") is not None


async def test_a_post_outside_the_window_is_not_collected(pool):
    source = FakeSource(
        [
            raw_post("inside", published_at=JUST_BEFORE_MIDNIGHT - timedelta(hours=2)),
            raw_post("outside", published_at=JUST_BEFORE_MIDNIGHT - timedelta(days=3)),
        ]
    )
    ingest = Ingest(pool, [source], interval_seconds=60, window_hours=24, clock=at(JUST_BEFORE_MIDNIGHT))

    await ingest.collect(source)

    async with pool.acquire() as conn:
        assert await store.post_by_external_id(conn, TRUTH_SOCIAL, "inside") is not None
        assert await store.post_by_external_id(conn, TRUTH_SOCIAL, "outside") is None


async def test_a_second_pass_over_the_same_posts_inserts_nothing(pool):
    source = FakeSource([raw_post("a", published_at=JUST_BEFORE_MIDNIGHT)])
    ingest = Ingest(pool, [source], interval_seconds=60, window_hours=24, clock=at(JUST_BEFORE_MIDNIGHT))

    first = await ingest.collect(source)
    second = await ingest.collect(source)

    assert (first.inserted, second.inserted) == (1, 0)


async def test_a_quiet_day_still_moves_the_moment_of_the_last_collection(pool):
    source = FakeSource([])
    ingest = Ingest(pool, [source], interval_seconds=60, window_hours=24, clock=at(JUST_BEFORE_MIDNIGHT))
    await ingest.start()
    await ingest.stop()

    result = await ingest.collect(source)

    assert result.succeeded
    async with pool.acquire() as conn:
        [state] = await store.collection_states(conn)
    assert state.last_success_at == JUST_BEFORE_MIDNIGHT


async def test_a_source_that_will_not_answer_leaves_the_archive_and_the_moment_alone(pool):
    answering = FakeSource([raw_post("a", published_at=JUST_BEFORE_MIDNIGHT)])
    ingest = Ingest(pool, [answering], interval_seconds=60, window_hours=24, clock=at(JUST_BEFORE_MIDNIGHT))
    await ingest.start()
    await ingest.stop()
    await ingest.collect(answering)

    silent = FakeSource(name=TRUTH_SOCIAL, fails_with="the feed did not answer")
    result = await ingest.collect(silent)

    assert result.failure == "the feed did not answer"
    async with pool.acquire() as conn:
        assert await store.count_in_window(
            conn, start=JUST_BEFORE_MIDNIGHT - timedelta(days=1), end=JUST_BEFORE_MIDNIGHT
        ) == 1
        [state] = await store.collection_states(conn)
    assert state.last_success_at == JUST_BEFORE_MIDNIGHT
    assert state.consecutive_failures == 1
    assert state.last_failure_reason == "the feed did not answer"


async def test_the_moment_collection_started_is_written_at_start_and_never_moved(pool):
    source = FakeSource([])
    ingest = Ingest(pool, [source], interval_seconds=60, window_hours=24, clock=at(JUST_BEFORE_MIDNIGHT))

    await ingest.start()
    await ingest.stop()
    async with pool.acquire() as conn:
        [first] = await store.collection_states(conn)

    await ingest.start()
    await ingest.stop()
    async with pool.acquire() as conn:
        [again] = await store.collection_states(conn)

    assert first.collecting_since == again.collecting_since


async def test_nothing_earlier_than_the_window_is_ever_asked_for(pool):
    """No backfill: the archive starts where it started, and a pass never reaches further back
    than its own window however empty the database is."""
    source = FakeSource([])
    ingest = Ingest(pool, [source], interval_seconds=60, window_hours=24, clock=at(JUST_BEFORE_MIDNIGHT))

    await ingest.collect(source)

    assert min(source.asked) == date(2026, 8, 30)


async def test_a_window_half_answered_writes_nothing_at_all(pool):
    """The first date answers and the second does not. Writing the half that arrived would leave an
    archive that cannot be told afterwards from a quiet stretch — and the next pass asks again."""
    early = raw_post("early", published_at=datetime(2026, 8, 30, 23, 50, tzinfo=UTC))
    source = FakeSource(
        by_day={date(2026, 8, 30): [early]}, fails_on=date(2026, 8, 31), name=TRUTH_SOCIAL
    )
    ingest = Ingest(
        pool, [source], interval_seconds=60, window_hours=24, clock=at(JUST_BEFORE_MIDNIGHT)
    )

    result = await ingest.collect(source)

    assert result.inserted == 0
    assert result.failure is not None
    async with pool.acquire() as conn:
        assert await store.post_by_external_id(conn, TRUTH_SOCIAL, "early") is None


async def test_a_read_never_adds_to_the_archive(pool, api):
    """The reversal this module is built on: in the application it came from, asking for a day's
    posts fetched the feed and wrote what it found."""
    source = FakeSource([raw_post("a", published_at=JUST_BEFORE_MIDNIGHT)])
    ingest = Ingest(
        pool, [source], interval_seconds=60, window_hours=24, clock=at(JUST_BEFORE_MIDNIGHT)
    )
    await ingest.collect(source)
    asked_before = len(source.asked)

    await api.get("/posts", params={"hours": 24})
    await api.get(f"/posts/{TRUTH_SOCIAL}/a")
    await api.get("/state")

    assert source.asked == source.asked[:asked_before]
    async with pool.acquire() as conn:
        assert await store.count_in_window(
            conn, start=JUST_BEFORE_MIDNIGHT - timedelta(days=1), end=JUST_BEFORE_MIDNIGHT
        ) == 1


async def test_the_loop_collects_without_anybody_asking(pool):
    """Started and left alone, the pass runs on its own interval — the property every other test
    here reaches past by calling `collect` directly."""
    source = FakeSource([raw_post("a", minutes_ago=5)])
    ingest = Ingest(pool, [source], interval_seconds=1, window_hours=24)

    await ingest.start()
    try:
        for _ in range(100):
            if source.asked:
                break
            await asyncio.sleep(0.02)
    finally:
        await ingest.stop()

    assert source.asked, "the loop asked its source for nothing"
    async with pool.acquire() as conn:
        assert await store.post_by_external_id(conn, TRUTH_SOCIAL, "a") is not None


async def test_a_finished_pass_beats_the_heartbeat(pool):
    """The rule itself is `tc-runtime`'s and tested there; this is the one test that the loop here
    actually asks for it — without which the metric an alert stands on reports a stopped loop."""
    heartbeat = LoopHeartbeat("collect", expected_seconds=60)
    ingest = Ingest(
        pool,
        [FakeSource([])],
        interval_seconds=60,
        window_hours=24,
        clock=at(JUST_BEFORE_MIDNIGHT),
        heartbeat=heartbeat,
    )

    await ingest.start()
    try:
        async with asyncio.timeout(5):
            while not heartbeat.has_run:
                await asyncio.sleep(0.01)
    finally:
        await ingest.stop()

    assert heartbeat.has_run
