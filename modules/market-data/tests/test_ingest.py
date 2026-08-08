from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest

from market_data.coverage import read_coverage
from market_data.errors import GatewayRefused, GatewayUnreachable
from market_data.gateway import CandleUpdate, FeedFailure, FeedState, FeedStatus, HistoryPage, Quote
from market_data.ingest import Backoff, Ingest, PairIngest, bars_to_close_gap, fill_gap
from market_data.models import Candle, CandleSource, Resolution
from market_data.rollups import read_derived
from market_data.store import read_candles, write_candles
from market_data.tracking import track, untrack

NOW = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)
LIMIT = 20


def minute_candle(offset: int, source: CandleSource = CandleSource.HISTORY, **overrides):
    """A minute candle `offset` minutes before NOW."""
    return Candle(
        **{
            "symbol": "US100",
            "resolution": Resolution.MINUTE,
            "period_start": NOW - timedelta(minutes=offset),
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 10.0,
            "source": source,
            **overrides,
        }
    )


class FakeHistory:
    """A gateway that records what it was asked for and answers with what it was given."""

    def __init__(self, candles=None, requests: int = 1, history_ended: bool = False, error=None):
        self.candles = candles if candles is not None else []
        self.requests = requests
        self.history_ended = history_ended
        self.error = error
        self.calls: list[tuple[str, Resolution, int]] = []

    async def history(self, symbol: str, resolution: Resolution, bars: int) -> HistoryPage:
        self.calls.append((symbol, resolution, bars))
        if self.error is not None:
            raise self.error
        return HistoryPage(
            symbol=symbol,
            resolution=resolution,
            candles=sorted(self.candles, key=lambda c: c.period_start),
            requested=bars,
            requests=self.requests,
            history_ended=self.history_ended,
        )


def fake_feed(*batches):
    """A `subscribe` that yields each batch of messages, then ends, then ends again.

    Each connection consumes one batch, so a caller that reconnects gets the next one and
    a caller that reconnects too often runs out — which is how a runaway loop shows up as
    a failure rather than as a hang.
    """
    remaining = list(batches)
    opened: list[int] = []

    @asynccontextmanager
    async def subscribe_to(url, symbol, resolution) -> AsyncIterator:
        opened.append(1)
        batch = remaining.pop(0) if remaining else []

        async def messages():
            for message in batch:
                yield message

        yield messages()

    subscribe_to.opened = opened
    return subscribe_to


@pytest.fixture
async def pool(migrated_url: str):
    from market_data.db import pool as make_pool

    async with make_pool(migrated_url, max_size=5) as created:
        async with created.acquire() as conn:
            await conn.execute("TRUNCATE candles, derived_candles, tracked_pairs, coverage_ranges")
        yield created


# --- the arithmetic that decides whether to ask at all (7.8) -------------------------


def test_a_pair_that_has_nothing_reaches_back_the_default() -> None:
    assert bars_to_close_gap(Resolution.MINUTE, None, NOW, default_bars=5_000) == 5_000


def test_a_current_pair_asks_for_nothing() -> None:
    # The newest closed candle is always up to one period old, because the current period
    # has not finished and the provider does not have it either. Treating that as a gap
    # would send a request every period, forever, for a candle nobody has yet.
    latest = NOW - timedelta(minutes=1)
    assert bars_to_close_gap(Resolution.MINUTE, latest, NOW, default_bars=5_000) == 0


def test_a_pair_one_period_behind_asks_for_nothing() -> None:
    latest = NOW - timedelta(minutes=1, seconds=59)
    assert bars_to_close_gap(Resolution.MINUTE, latest, NOW, default_bars=5_000) == 0


def test_a_pair_behind_by_a_break_asks_for_what_it_missed() -> None:
    latest = NOW - timedelta(minutes=30)
    # Twenty-nine missing periods plus a little overlap, so the seam is covered twice
    # rather than nearly.
    assert bars_to_close_gap(Resolution.MINUTE, latest, NOW, default_bars=5_000) == 31


def test_the_gap_is_measured_in_the_pair_s_own_periods() -> None:
    latest = NOW - timedelta(hours=5)
    assert bars_to_close_gap(Resolution.HOUR, latest, NOW, default_bars=5_000) == 6
    assert bars_to_close_gap(Resolution.DAY, latest, NOW, default_bars=5_000) == 0


def test_a_request_is_never_larger_than_the_gateway_accepts() -> None:
    # The gateway refuses more than 50 000 with a validation error rather than clamping.
    assert bars_to_close_gap(Resolution.MINUTE, None, NOW, default_bars=200_000) == 50_000
    latest = NOW - timedelta(days=365)
    assert bars_to_close_gap(Resolution.MINUTE, latest, NOW, default_bars=100) == 50_000


# --- 7.3 and 7.8: filling, and not filling -------------------------------------------


@pytest.mark.db
async def test_a_start_after_a_break_fetches_the_missing_stretch(pool) -> None:
    """7.8, first half."""
    async with pool.acquire() as conn:
        await write_candles(conn, [minute_candle(30)])
    history = FakeHistory([minute_candle(m) for m in range(1, 30)])

    outcome = await fill_gap(
        pool, history, "US100", Resolution.MINUTE, default_bars=5_000, now=NOW
    )

    assert len(history.calls) == 1
    assert outcome.written == 29
    async with pool.acquire() as conn:
        assert len(await read_candles(conn, "US100", Resolution.MINUTE)) == 30


@pytest.mark.db
async def test_a_start_without_a_break_sends_no_request(pool) -> None:
    """7.8, second half — the half that costs the provider's budget when it is wrong."""
    async with pool.acquire() as conn:
        await write_candles(conn, [minute_candle(1)])
    history = FakeHistory([minute_candle(m) for m in range(1, 30)])

    outcome = await fill_gap(
        pool, history, "US100", Resolution.MINUTE, default_bars=5_000, now=NOW
    )

    assert history.calls == []
    assert outcome.requested == 0
    assert outcome.asked_the_provider is False


@pytest.mark.db
async def test_a_first_fill_reaches_back_the_configured_depth(pool) -> None:
    history = FakeHistory([minute_candle(m) for m in range(1, 5)])

    await fill_gap(pool, history, "US100", Resolution.MINUTE, default_bars=5_000, now=NOW)

    assert history.calls == [("US100", Resolution.MINUTE, 5_000)]


@pytest.mark.db
async def test_a_fill_is_one_request_however_deep(pool) -> None:
    # The gateway pages past the provider's ceiling itself and owns the rate gate. A
    # second pager here would drift from it and spend the budget twice.
    history = FakeHistory([minute_candle(m) for m in range(1, 5)], requests=63)

    outcome = await fill_gap(
        pool, history, "US100", Resolution.MINUTE, default_bars=50_000, now=NOW
    )

    assert len(history.calls) == 1
    assert outcome.requests == 63  # what it cost upstream, passed through


@pytest.mark.db
async def test_a_fill_records_what_it_verified(pool) -> None:
    history = FakeHistory([minute_candle(m) for m in range(1, 30)])

    await fill_gap(pool, history, "US100", Resolution.MINUTE, default_bars=5_000, now=NOW)

    async with pool.acquire() as conn:
        [covered] = await read_coverage(conn, "US100", Resolution.MINUTE)
    assert covered.range_start == NOW - timedelta(minutes=29)
    # Up to the moment of the read, not the newest candle. Those differ exactly when the
    # market was shut for the tail of the window, and recording only as far as the last
    # candle is what would send this same request again tomorrow, and every day after.
    assert covered.range_end >= NOW


@pytest.mark.db
async def test_the_end_of_provider_history_is_recorded_as_a_boundary(pool) -> None:
    history = FakeHistory([minute_candle(m) for m in range(1, 5)], history_ended=True)

    outcome = await fill_gap(
        pool, history, "US100", Resolution.MINUTE, default_bars=5_000, now=NOW
    )

    assert outcome.history_ended is True
    async with pool.acquire() as conn:
        [covered] = await read_coverage(conn, "US100", Resolution.MINUTE)
    assert covered.history_ended is True


@pytest.mark.db
async def test_a_minute_fill_folds_into_the_derived_resolutions(pool) -> None:
    history = FakeHistory([minute_candle(m) for m in range(1, 20)])

    await fill_gap(pool, history, "US100", Resolution.MINUTE, default_bars=5_000, now=NOW)

    async with pool.acquire() as conn:
        assert await read_derived(conn, "US100", Resolution.MINUTE_5)


@pytest.mark.db
async def test_an_empty_answer_verifies_nothing(pool) -> None:
    # The gateway pages backwards from now, so with no candles at all there is no telling
    # how far back it looked. Claiming coverage would be claiming to have checked a
    # stretch nobody checked.
    history = FakeHistory([])

    await fill_gap(pool, history, "US100", Resolution.MINUTE, default_bars=5_000, now=NOW)

    async with pool.acquire() as conn:
        assert await read_coverage(conn, "US100", Resolution.MINUTE) == []


# --- 7.7: saying what happened -------------------------------------------------------


@pytest.mark.db
async def test_a_failed_fill_names_its_reason_and_does_not_raise(pool) -> None:
    # One pair's failure is not a reason to stop collecting the others, so it comes back
    # as an outcome rather than an exception — but it must not come back looking like
    # success either.
    history = FakeHistory(error=GatewayRefused(404, "unknown symbol 'NOPE'"))

    outcome = await fill_gap(
        pool, history, "NOPE", Resolution.MINUTE, default_bars=5_000, now=NOW
    )

    assert outcome.failure is not None
    assert "unknown symbol" in outcome.failure
    assert outcome.written == 0


@pytest.mark.db
async def test_an_unreachable_gateway_is_reported_not_raised(pool) -> None:
    history = FakeHistory(error=GatewayUnreachable("connection refused"))

    outcome = await fill_gap(
        pool, history, "US100", Resolution.MINUTE, default_bars=5_000, now=NOW
    )

    assert outcome.failure is not None


def test_an_outcome_reads_as_a_sentence() -> None:
    from market_data.ingest import FillOutcome

    current = FillOutcome(symbol="US100", resolution=Resolution.MINUTE, requested=0)
    assert "already current" in current.describe()

    filled = FillOutcome(
        symbol="US100", resolution=Resolution.MINUTE, requested=100, written=97, requests=3
    )
    assert "wrote 97" in filled.describe()
    assert "3 provider request" in filled.describe()

    failed = FillOutcome(
        symbol="US100", resolution=Resolution.MINUTE, requested=100, failure="the gateway refused"
    )
    assert "failed" in failed.describe()


# --- 7.6: the budget -----------------------------------------------------------------


@pytest.mark.db
async def test_fills_do_not_run_more_at_once_than_the_budget_allows(pool) -> None:
    """The gateway's rate gate is the provider's ten a second counted against the account,
    so the ceiling has to be held in one place every fill queues behind."""
    in_flight = 0
    peak = 0

    class SlowHistory(FakeHistory):
        async def history(self, symbol, resolution, bars):
            nonlocal in_flight, peak
            in_flight += 1
            peak = max(peak, in_flight)
            await asyncio.sleep(0.02)
            in_flight -= 1
            return await super().history(symbol, resolution, bars)

    limiter = asyncio.Semaphore(1)
    histories = [SlowHistory([minute_candle(1, symbol=f"SYM{n}")]) for n in range(5)]
    await asyncio.gather(
        *(
            fill_gap(
                pool,
                history,
                f"SYM{n}",
                Resolution.MINUTE,
                default_bars=100,
                limiter=limiter,
                now=NOW,
            )
            for n, history in enumerate(histories)
        )
    )

    assert peak == 1


@pytest.mark.db
async def test_a_larger_budget_lets_more_run(pool) -> None:
    # The budget is a setting rather than a hardcoded one-at-a-time, so it has to
    # actually be the thing controlling this.
    in_flight = 0
    peak = 0

    class SlowHistory(FakeHistory):
        async def history(self, symbol, resolution, bars):
            nonlocal in_flight, peak
            in_flight += 1
            peak = max(peak, in_flight)
            await asyncio.sleep(0.02)
            in_flight -= 1
            return await super().history(symbol, resolution, bars)

    limiter = asyncio.Semaphore(3)
    await asyncio.gather(
        *(
            fill_gap(
                pool,
                SlowHistory([minute_candle(1, symbol=f"SYM{n}")]),
                f"SYM{n}",
                Resolution.MINUTE,
                default_bars=100,
                limiter=limiter,
                now=NOW,
            )
            for n in range(5)
        )
    )

    assert peak == 3


@pytest.mark.db
async def test_deciding_not_to_fetch_never_waits_for_the_budget(pool) -> None:
    # The limiter is taken around the provider call only. A pair that needs nothing must
    # not queue behind another pair's deep fill just to discover that.
    async with pool.acquire() as conn:
        await write_candles(conn, [minute_candle(1)])
    held = asyncio.Semaphore(1)
    await held.acquire()  # nothing can pass this

    outcome = await asyncio.wait_for(
        fill_gap(
            pool,
            FakeHistory([]),
            "US100",
            Resolution.MINUTE,
            default_bars=5_000,
            limiter=held,
            now=NOW,
        ),
        timeout=2,
    )

    assert outcome.requested == 0


# --- 7.1, 7.2, 7.5: the live loop ----------------------------------------------------


@pytest.mark.db
async def test_a_closed_candle_from_the_feed_is_stored(pool) -> None:
    tracked = [True, False]  # collect once, then the pair stops being tracked
    feed = fake_feed([CandleUpdate(candle=minute_candle(1, source=CandleSource.STREAM))])

    await PairIngest(
        pool=pool,
        history=FakeHistory([]),
        stream_url="ws://gateway.test/ws/stream",
        symbol="US100",
        resolution=Resolution.MINUTE,
        default_bars=100,
        still_tracked=_tracked_then_not(tracked),
        subscribe_to=feed,
        sleep=_no_sleep,
    ).run()

    async with pool.acquire() as conn:
        [stored] = await read_candles(conn, "US100", Resolution.MINUTE)
    assert stored.source is CandleSource.STREAM


@pytest.mark.db
async def test_a_forming_candle_from_the_feed_is_not_stored(pool) -> None:
    forming = minute_candle(0, source=CandleSource.STREAM, forming=True)
    feed = fake_feed([CandleUpdate(candle=forming)])

    await PairIngest(
        pool=pool,
        history=FakeHistory([]),
        stream_url="ws://gateway.test/ws/stream",
        symbol="US100",
        resolution=Resolution.MINUTE,
        default_bars=100,
        still_tracked=_tracked_then_not([True, False]),
        subscribe_to=feed,
        sleep=_no_sleep,
    ).run()

    async with pool.acquire() as conn:
        assert await read_candles(conn, "US100", Resolution.MINUTE) == []


@pytest.mark.db
async def test_the_gateway_reporting_trouble_closes_the_gap_it_left(pool) -> None:
    """Caught on the live feed, and invisible to every test that existed.

    A keepalive timeout between the gateway and the provider does not close the socket
    to us. The listening loop therefore never ends, the gap-closing at the top of `run`
    never comes round, and the minutes the gateway spent disconnected stay missing —
    measured on 2026-08-08 as two candles the provider still had, correctly reported as
    uncovered and never fetched again until a restart.
    """
    missed = [minute_candle(2), minute_candle(1)]
    history = FakeHistory(missed)
    feed = fake_feed(
        [
            FeedStatus(state=FeedState.CONNECTED),
            FeedFailure(message="sent 1011 (internal error) keepalive ping timeout"),
        ]
    )

    await PairIngest(
        pool=pool,
        history=history,
        stream_url="ws://gateway.test/ws/stream",
        symbol="US100",
        resolution=Resolution.MINUTE,
        default_bars=100,
        still_tracked=_tracked_then_not([True, True, False]),
        subscribe_to=feed,
        sleep=_no_sleep,
    ).run()

    # Twice: once at the top of the loop, once on hearing the gateway say it had trouble.
    assert len(history.calls) >= 2
    async with pool.acquire() as conn:
        stored = await read_candles(conn, "US100", Resolution.MINUTE)
    assert len(stored) == 2  # the stretch nobody was listening for came back


@pytest.mark.db
async def test_quotes_and_status_do_not_become_candles(pool) -> None:
    feed = fake_feed(
        [
            FeedStatus(state=FeedState.CONNECTED),
            Quote(symbol="US100", at=NOW, bid=100.4, ask=100.6),
            FeedFailure(message="upstream hiccup"),
        ]
    )

    await PairIngest(
        pool=pool,
        history=FakeHistory([]),
        stream_url="ws://gateway.test/ws/stream",
        symbol="US100",
        resolution=Resolution.MINUTE,
        default_bars=100,
        still_tracked=_tracked_then_not([True, False]),
        subscribe_to=feed,
        sleep=_no_sleep,
    ).run()

    async with pool.acquire() as conn:
        assert await read_candles(conn, "US100", Resolution.MINUTE) == []


@pytest.mark.db
async def test_a_dropped_feed_is_resumed_while_the_pair_is_tracked(pool) -> None:
    """7.2."""
    feed = fake_feed([], [], [])  # three connections, each ending straight away
    delays: list[float] = []

    async def record(delay: float) -> None:
        delays.append(delay)

    await PairIngest(
        pool=pool,
        history=FakeHistory([]),
        stream_url="ws://gateway.test/ws/stream",
        symbol="US100",
        resolution=Resolution.MINUTE,
        default_bars=100,
        still_tracked=tracked_until_opened(feed, 3),
        subscribe_to=feed,
        sleep=record,
    ).run()

    assert len(feed.opened) == 3
    assert delays == [1.0, 2.0]  # growing, so an outage does not become a retry storm


@pytest.mark.db
async def test_the_wait_stops_growing_at_the_cap(pool) -> None:
    # A feed that comes back after an hour should be picked up in a minute, not an hour.
    backoff = Backoff(first=1.0, cap=4.0, factor=2.0)
    assert [backoff.next_delay() for _ in range(5)] == [1.0, 2.0, 4.0, 4.0, 4.0]


@pytest.mark.db
async def test_a_feed_that_produced_something_starts_over_from_the_first_delay(
    pool,
) -> None:
    backoff = Backoff(first=1.0, cap=60.0)
    backoff.next_delay()
    backoff.next_delay()

    backoff.reset()

    assert backoff.next_delay() == 1.0


@pytest.mark.db
async def test_a_resumed_subscription_closes_the_gap_it_left(pool) -> None:
    """7.5. Reconnecting without fetching leaves a hole that looks exactly like a market
    that was shut."""
    async with pool.acquire() as conn:
        await write_candles(conn, [minute_candle(30)])
    history = FakeHistory([minute_candle(m) for m in range(1, 30)])
    feed = fake_feed([], [])

    await PairIngest(
        pool=pool,
        history=history,
        stream_url="ws://gateway.test/ws/stream",
        symbol="US100",
        resolution=Resolution.MINUTE,
        default_bars=100,
        still_tracked=tracked_until_opened(feed, 2),
        subscribe_to=feed,
        sleep=_no_sleep,
    ).run()

    # Once before the first subscription and once before the second: the second is the
    # gap the dropped connection left.
    assert len(history.calls) == 2


@pytest.mark.db
async def test_the_loop_ends_when_the_pair_stops_being_tracked(pool) -> None:
    feed = fake_feed([], [], [], [])

    await PairIngest(
        pool=pool,
        history=FakeHistory([]),
        stream_url="ws://gateway.test/ws/stream",
        symbol="US100",
        resolution=Resolution.MINUTE,
        default_bars=100,
        still_tracked=_tracked_then_not([False]),
        subscribe_to=feed,
        sleep=_no_sleep,
    ).run()

    assert feed.opened == []


# --- 7.4 and the supervisor ----------------------------------------------------------


@pytest.mark.db
async def test_every_tracked_pair_is_collected_from_a_cold_start(pool) -> None:
    """7.4."""
    async with pool.acquire() as conn:
        await track(conn, "US100", Resolution.MINUTE, LIMIT)
        await track(conn, "GOLD", Resolution.HOUR, LIMIT)

    ingest = Ingest(
        pool,
        FakeHistory([]),
        "ws://gateway.test/ws/stream",
        default_bars=100,
        subscribe_to=_never_ending_feed,
        sleep=_no_sleep,
    )
    await ingest.start()
    try:
        await asyncio.sleep(0.05)
        assert ingest.running == {
            ("US100", Resolution.MINUTE),
            ("GOLD", Resolution.HOUR),
        }
    finally:
        await ingest.stop()

    assert ingest.running == set()


@pytest.mark.db
async def test_a_pair_added_later_is_collected_without_a_restart(pool) -> None:
    ingest = Ingest(
        pool,
        FakeHistory([]),
        "ws://gateway.test/ws/stream",
        default_bars=100,
        subscribe_to=_never_ending_feed,
        sleep=_no_sleep,
    )
    await ingest.start()
    try:
        assert ingest.running == set()

        async with pool.acquire() as conn:
            await track(conn, "US100", Resolution.MINUTE, LIMIT)
        await ingest.sync()

        assert ingest.running == {("US100", Resolution.MINUTE)}
    finally:
        await ingest.stop()


@pytest.mark.db
async def test_an_untracked_pair_stops_being_collected(pool) -> None:
    async with pool.acquire() as conn:
        await track(conn, "US100", Resolution.MINUTE, LIMIT)

    ingest = Ingest(
        pool,
        FakeHistory([]),
        "ws://gateway.test/ws/stream",
        default_bars=100,
        subscribe_to=_never_ending_feed,
        sleep=_no_sleep,
    )
    await ingest.start()
    try:
        async with pool.acquire() as conn:
            await untrack(conn, "US100", Resolution.MINUTE)
        await ingest.sync()

        assert ingest.running == set()
    finally:
        await ingest.stop()


@pytest.mark.db
async def test_the_supervisor_reports_what_each_fill_did(pool) -> None:
    """7.7."""
    async with pool.acquire() as conn:
        await track(conn, "US100", Resolution.MINUTE, LIMIT)
    history = FakeHistory([minute_candle(m) for m in range(1, 5)])

    ingest = Ingest(
        pool,
        history,
        "ws://gateway.test/ws/stream",
        default_bars=100,
        subscribe_to=_never_ending_feed,
        sleep=_no_sleep,
    )
    await ingest.start()
    try:
        await asyncio.sleep(0.1)
        outcome = ingest.last_fill("US100", Resolution.MINUTE)
    finally:
        await ingest.stop()

    assert outcome is not None
    assert outcome.written == 4
    assert "wrote 4" in outcome.describe()


# --- helpers -------------------------------------------------------------------------


def tracked_until_opened(feed, times: int):
    """A `still_tracked` that keeps the loop going until the feed has been opened `times`.

    Counting connections rather than scripting a list of booleans: the loop asks
    `still_tracked` at several points per pass, so a list encodes how the loop is written
    instead of what the test means, and answers the wrong question the moment the loop
    changes shape.
    """

    async def still_tracked() -> bool:
        return len(feed.opened) < times

    return still_tracked


def _tracked_then_not(answers: list[bool]):
    """For the tests that want exactly one pass, or none."""
    remaining = list(answers)

    async def still_tracked() -> bool:
        return remaining.pop(0) if remaining else False

    return still_tracked


async def _no_sleep(_delay: float) -> None:
    return None


@asynccontextmanager
async def _never_ending_feed(url, symbol, resolution):
    """A feed that stays open and says nothing, so a supervisor test is about supervision
    rather than about what the feed happened to send."""

    async def messages():
        while True:
            await asyncio.sleep(3600)
            yield  # pragma: no cover

    yield messages()
