from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import asyncpg
import httpx
import pytest
import respx

from market_data.db import asyncpg_dsn
from market_data.errors import GatewayUnreachable
from market_data.gateway import GatewayInstruments
from market_data.models import Candle, CandleSource, Resolution, TrackedPairState
from market_data.store import write_candles
from market_data.tracking import (
    CollectionState,
    LimitReached,
    UnknownPair,
    add_pair,
    collection_state,
    default_collect_from,
    is_tracked,
    read_all,
    read_status,
    read_tracked,
    track,
    untrack,
)

MOMENT = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)
BASE_URL = "http://gateway.test:8010"
LIMIT = 20


def candle(symbol: str = "US100", resolution: Resolution = Resolution.MINUTE, **overrides):
    return Candle(
        **{
            "symbol": symbol,
            "resolution": resolution,
            "period_start": MOMENT,
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "source": CandleSource.HISTORY,
            **overrides,
        }
    )


# --- 6.4: the rule, on its own ------------------------------------------------------


def test_a_pair_that_has_collected_nothing_says_so() -> None:
    assert (
        collection_state(Resolution.MINUTE, None, MOMENT) is CollectionState.NEVER_COLLECTED
    )


def test_a_fresh_series_is_collecting() -> None:
    latest = MOMENT - timedelta(minutes=1)
    assert collection_state(Resolution.MINUTE, latest, MOMENT, True) is CollectionState.COLLECTING


def test_one_period_behind_is_not_yet_a_fault() -> None:
    # A candle is only written once its period closes, so the newest one is legitimately
    # up to a period old at any moment. A threshold of one period would call every
    # healthy pair broken, every period.
    latest = MOMENT - timedelta(minutes=1, seconds=30)
    assert collection_state(Resolution.MINUTE, latest, MOMENT, True) is CollectionState.COLLECTING


def test_exactly_two_periods_behind_is_still_collecting() -> None:
    latest = MOMENT - timedelta(minutes=2)
    assert collection_state(Resolution.MINUTE, latest, MOMENT, True) is CollectionState.COLLECTING


def test_more_than_two_periods_behind_with_the_market_open_has_stalled() -> None:
    # The scenario this exists for: a subscription that died without a sound. The only
    # visible symptom is a series that stopped growing while the market is open.
    latest = MOMENT - timedelta(minutes=10)
    assert collection_state(Resolution.MINUTE, latest, MOMENT, True) is CollectionState.STALLED


def test_a_candle_still_on_its_way_is_not_a_stall() -> None:
    """Measured on the live feed, and the reason `DELIVERY_GRACE` exists.

    A closed minute candle took 52 to 169 seconds to arrive, so a perfectly healthy pair
    sits well past two periods behind for part of every minute. Without the grace the
    state flipped between COLLECTING and STALLED from one read to the next, which teaches
    an operator to ignore the one indicator that is supposed to matter.
    """
    for lag in (timedelta(seconds=112), timedelta(seconds=229)):
        assert (
            collection_state(Resolution.MINUTE, MOMENT - lag, MOMENT, True)
            is CollectionState.COLLECTING
        ), f"{lag} behind is what arriving normally looks like"


def test_the_grace_does_not_scale_with_the_period() -> None:
    """A fixed span, not a third period. At HOUR a third period would be another hour of
    a dead feed going unreported; the delivery itself takes the same few seconds at every
    resolution."""
    assert (
        collection_state(Resolution.HOUR, MOMENT - timedelta(hours=2, minutes=10), MOMENT, True)
        is CollectionState.STALLED
    )


def test_the_same_lateness_with_the_market_shut_is_not_a_fault() -> None:
    latest = MOMENT - timedelta(days=2)
    assert (
        collection_state(Resolution.MINUTE, latest, MOMENT, False) is CollectionState.MARKET_CLOSED
    )


def test_lateness_with_nobody_saying_whether_the_market_is_open_is_unknown() -> None:
    # An honest third answer. This module has no session calendar, and inventing one
    # would produce a confident wrong answer twice a day.
    latest = MOMENT - timedelta(days=2)
    assert collection_state(Resolution.MINUTE, latest, MOMENT, None) is CollectionState.UNKNOWN


def test_lateness_is_measured_in_the_pair_s_own_periods() -> None:
    # Ten minutes is stale for a minute series and perfectly fresh for an hourly one.
    latest = MOMENT - timedelta(minutes=10)
    assert collection_state(Resolution.MINUTE, latest, MOMENT, True) is CollectionState.STALLED
    assert collection_state(Resolution.HOUR, latest, MOMENT, True) is CollectionState.COLLECTING


# --- 6.1 and 6.6: taking a pair on ---------------------------------------------------


@pytest.mark.db
async def test_a_tracked_pair_reads_back(db: asyncpg.Connection) -> None:
    await track(db, "US100", Resolution.MINUTE, LIMIT)

    [tracked] = await read_tracked(db)
    assert (tracked.symbol, tracked.resolution) == ("US100", Resolution.MINUTE)
    assert tracked.state is TrackedPairState.TRACKED
    assert tracked.untracked_at is None
    assert await is_tracked(db, "US100", Resolution.MINUTE) is True


@pytest.mark.db
async def test_the_same_pair_tracked_twice_is_one_pair(db: asyncpg.Connection) -> None:
    await track(db, "US100", Resolution.MINUTE, LIMIT)
    await track(db, "US100", Resolution.MINUTE, LIMIT)

    assert len(await read_tracked(db)) == 1


@pytest.mark.db
async def test_a_symbol_at_two_resolutions_is_two_pairs(db: asyncpg.Connection) -> None:
    # Each holds its own provider connection, so each counts against the ceiling.
    await track(db, "US100", Resolution.MINUTE, LIMIT)
    await track(db, "US100", Resolution.HOUR, LIMIT)

    assert len(await read_tracked(db)) == 2


@pytest.mark.db
async def test_going_over_the_ceiling_is_refused_with_the_reason(
    db: asyncpg.Connection,
) -> None:
    """6.6. The ceiling is real — the gateway holds one provider connection per pair and
    the provider limits sessions — so the refusal has to name it rather than silently
    accepting a pair nothing will collect."""
    for n in range(3):
        await track(db, f"SYM{n}", Resolution.MINUTE, limit=3)

    with pytest.raises(LimitReached) as err:
        await track(db, "ONE_TOO_MANY", Resolution.MINUTE, limit=3)

    assert "ceiling of 3" in str(err.value)
    assert "MAX_TRACKED_PAIRS" in str(err.value)


@pytest.mark.db
async def test_the_pairs_already_tracked_are_untouched_by_a_refusal(
    db: asyncpg.Connection,
) -> None:
    for n in range(3):
        await track(db, f"SYM{n}", Resolution.MINUTE, limit=3)

    with pytest.raises(LimitReached):
        await track(db, "ONE_TOO_MANY", Resolution.MINUTE, limit=3)

    assert len(await read_tracked(db)) == 3
    assert await is_tracked(db, "ONE_TOO_MANY", Resolution.MINUTE) is False


@pytest.mark.db
async def test_re_tracking_at_the_ceiling_is_allowed(db: asyncpg.Connection) -> None:
    # It costs no new provider connection, so refusing it would be a ceiling enforced
    # against an action that does not spend the thing the ceiling protects.
    for n in range(3):
        await track(db, f"SYM{n}", Resolution.MINUTE, limit=3)

    await track(db, "SYM0", Resolution.MINUTE, limit=3)

    assert len(await read_tracked(db)) == 3


@pytest.mark.db
async def test_an_untracked_pair_frees_a_place(db: asyncpg.Connection) -> None:
    for n in range(3):
        await track(db, f"SYM{n}", Resolution.MINUTE, limit=3)
    await untrack(db, "SYM0", Resolution.MINUTE)

    await track(db, "SYM3", Resolution.MINUTE, limit=3)

    assert {p.symbol for p in await read_tracked(db)} == {"SYM1", "SYM2", "SYM3"}


@pytest.mark.db
async def test_additions_racing_each_other_cannot_overrun_the_ceiling(
    db: asyncpg.Connection, migrated_url: str
) -> None:
    """Counting and inserting have to be one atomic thing.

    Without the lock they are not: several additions read the same count, all decide
    there is room, and the archive ends up over a ceiling the provider itself enforces.

    Eight at once rather than two. Two interleave only sometimes — the version of this
    test that used a pair passed against a deliberately unlocked implementation, which
    makes it worse than no test at all. Eight fails every time.
    """
    conns = [await asyncpg.connect(asyncpg_dsn(migrated_url)) for _ in range(8)]
    try:
        outcomes = await asyncio.gather(
            *(track(c, f"SYM{n}", Resolution.MINUTE, limit=2) for n, c in enumerate(conns)),
            return_exceptions=True,
        )
    finally:
        for c in conns:
            await c.close()

    assert sum(isinstance(o, LimitReached) for o in outcomes) == 6
    assert len(await read_tracked(db)) == 2


# --- 6.2: letting a pair go ----------------------------------------------------------


@pytest.mark.db
async def test_untracking_stops_collection(db: asyncpg.Connection) -> None:
    await track(db, "US100", Resolution.MINUTE, LIMIT)

    await untrack(db, "US100", Resolution.MINUTE)

    assert await read_tracked(db) == []
    assert await is_tracked(db, "US100", Resolution.MINUTE) is False


@pytest.mark.db
async def test_untracking_keeps_every_candle(db: asyncpg.Connection) -> None:
    # An archive that discards data when its configuration changes is not an archive.
    await track(db, "US100", Resolution.MINUTE, LIMIT)
    await write_candles(db, [candle()])

    await untrack(db, "US100", Resolution.MINUTE)

    assert await db.fetchval("SELECT count(*) FROM candles") == 1


@pytest.mark.db
async def test_untracking_records_when_collection_stopped(db: asyncpg.Connection) -> None:
    # The left edge of the gap that tracking it again will have to close.
    await track(db, "US100", Resolution.MINUTE, LIMIT)

    stopped = await untrack(db, "US100", Resolution.MINUTE)

    assert stopped is not None
    assert stopped.state is TrackedPairState.UNTRACKED
    assert stopped.untracked_at is not None


@pytest.mark.db
async def test_untracking_a_pair_that_was_not_tracked_says_nothing_happened(
    db: asyncpg.Connection,
) -> None:
    assert await untrack(db, "US100", Resolution.MINUTE) is None


@pytest.mark.db
async def test_a_stopped_pair_is_still_on_the_record(db: asyncpg.Connection) -> None:
    await track(db, "US100", Resolution.MINUTE, LIMIT)
    await untrack(db, "US100", Resolution.MINUTE)

    assert [p.state for p in await read_all(db)] == [TrackedPairState.UNTRACKED]


@pytest.mark.db
async def test_tracking_a_stopped_pair_again_resumes_the_same_decision(
    db: asyncpg.Connection,
) -> None:
    original = await track(db, "US100", Resolution.MINUTE, LIMIT)
    await untrack(db, "US100", Resolution.MINUTE)

    resumed = await track(db, "US100", Resolution.MINUTE, LIMIT)

    assert resumed.added_at == original.added_at
    assert resumed.untracked_at is None
    assert len(await read_all(db)) == 1


# --- 6.5: the configuration outliving the process ------------------------------------


@pytest.mark.db
async def test_the_configuration_survives_a_restart(
    db: asyncpg.Connection, migrated_url: str
) -> None:
    """6.5. There is no list in a file to disagree with this — a restart reads the rows,
    and the rows are what the operator decided."""
    await track(db, "US100", Resolution.MINUTE, LIMIT)
    await track(db, "GOLD", Resolution.HOUR, LIMIT)
    await untrack(db, "GOLD", Resolution.HOUR)
    await track(db, "BTCUSD", Resolution.MINUTE_5, LIMIT)

    # A second connection stands in for the process that comes up next: nothing is carried
    # over in memory, only what was written down.
    after_restart = await asyncpg.connect(asyncpg_dsn(migrated_url))
    try:
        resumed = await read_tracked(after_restart)
    finally:
        await after_restart.close()

    assert {(p.symbol, p.resolution) for p in resumed} == {
        ("US100", Resolution.MINUTE),
        ("BTCUSD", Resolution.MINUTE_5),
    }


# --- 6.3: the list, with how each pair is doing ---------------------------------------


@pytest.mark.db
async def test_the_status_carries_the_newest_candle(db: asyncpg.Connection) -> None:
    await track(db, "US100", Resolution.MINUTE, LIMIT)
    await write_candles(
        db,
        [candle(period_start=MOMENT - timedelta(minutes=m)) for m in range(3)],
    )

    [status] = await read_status(db, now=MOMENT)

    assert status.symbol == "US100"
    assert status.latest_candle == MOMENT


@pytest.mark.db
async def test_a_pair_that_has_collected_nothing_still_appears(
    db: asyncpg.Connection,
) -> None:
    # Being missing from the list and having collected nothing look the same to an
    # operator, and only one of them is what happened.
    await track(db, "US100", Resolution.MINUTE, LIMIT)

    [status] = await read_status(db, now=MOMENT)

    assert status.latest_candle is None
    assert status.collection is CollectionState.NEVER_COLLECTED


@pytest.mark.db
async def test_an_untracked_pair_is_not_in_the_status_list(db: asyncpg.Connection) -> None:
    await track(db, "US100", Resolution.MINUTE, LIMIT)
    await untrack(db, "US100", Resolution.MINUTE)

    assert await read_status(db, now=MOMENT) == []


@pytest.mark.db
async def test_the_status_reports_collection_stalled_when_the_market_is_open(
    db: asyncpg.Connection,
) -> None:
    await track(db, "US100", Resolution.MINUTE, LIMIT)
    await write_candles(db, [candle(period_start=MOMENT - timedelta(hours=1))])

    [status] = await read_status(
        db, market_open={("US100", Resolution.MINUTE): True}, now=MOMENT
    )

    assert status.collection is CollectionState.STALLED


@pytest.mark.db
async def test_the_status_does_not_call_a_shut_market_a_fault(db: asyncpg.Connection) -> None:
    await track(db, "US100", Resolution.MINUTE, LIMIT)
    await write_candles(db, [candle(period_start=MOMENT - timedelta(hours=1))])

    [status] = await read_status(
        db, market_open={("US100", Resolution.MINUTE): False}, now=MOMENT
    )

    assert status.collection is CollectionState.MARKET_CLOSED


@pytest.mark.db
async def test_each_pair_is_judged_by_its_own_candles(db: asyncpg.Connection) -> None:
    await track(db, "US100", Resolution.MINUTE, LIMIT)
    await track(db, "GOLD", Resolution.MINUTE, LIMIT)
    await write_candles(db, [candle(symbol="US100", period_start=MOMENT)])
    await write_candles(
        db, [candle(symbol="GOLD", period_start=MOMENT - timedelta(hours=1))]
    )

    open_now = {("US100", Resolution.MINUTE): True, ("GOLD", Resolution.MINUTE): True}
    by_symbol = {s.symbol: s for s in await read_status(db, market_open=open_now, now=MOMENT)}

    assert by_symbol["US100"].collection is CollectionState.COLLECTING
    assert by_symbol["GOLD"].collection is CollectionState.STALLED


@pytest.mark.db
async def test_candles_at_another_resolution_do_not_count_as_freshness(
    db: asyncpg.Connection,
) -> None:
    # A pair tracked at MINUTE is not kept alive by an hourly series for the same symbol.
    await track(db, "US100", Resolution.MINUTE, LIMIT)
    await write_candles(db, [candle(resolution=Resolution.HOUR, period_start=MOMENT)])

    [status] = await read_status(db, now=MOMENT)

    assert status.latest_candle is None
    assert status.collection is CollectionState.NEVER_COLLECTED


# --- 6.1: validation against the gateway ---------------------------------------------


@pytest.fixture
async def instruments():
    async with httpx.AsyncClient() as client:
        yield GatewayInstruments(BASE_URL, client)


@respx.mock
@pytest.mark.db
async def test_a_pair_the_gateway_can_serve_is_taken_on(
    db: asyncpg.Connection, instruments: GatewayInstruments
) -> None:
    respx.get(f"{BASE_URL}/instruments/US100/candles").mock(
        return_value=httpx.Response(200, json=[{"ts": "2026-08-07T12:00:00Z", "close": 1.0}])
    )

    await add_pair(db, instruments, "US100", Resolution.MINUTE, LIMIT)

    assert await is_tracked(db, "US100", Resolution.MINUTE) is True


@respx.mock
@pytest.mark.db
async def test_a_symbol_the_provider_does_not_know_is_refused(
    db: asyncpg.Connection, instruments: GatewayInstruments
) -> None:
    respx.get(f"{BASE_URL}/instruments/NOPE/candles").mock(
        return_value=httpx.Response(404, json={"detail": "unknown symbol 'NOPE'"})
    )

    with pytest.raises(UnknownPair, match="unknown symbol"):
        await add_pair(db, instruments, "NOPE", Resolution.MINUTE, LIMIT)

    assert await read_tracked(db) == []


@respx.mock
@pytest.mark.db
async def test_a_symbol_with_no_series_at_that_resolution_is_refused(
    db: asyncpg.Connection, instruments: GatewayInstruments
) -> None:
    # It would sit on the list forever, holding a provider connection and archiving
    # nothing.
    respx.get(f"{BASE_URL}/instruments/QUIET/candles").mock(
        return_value=httpx.Response(200, json=[])
    )

    with pytest.raises(UnknownPair, match="archive nothing"):
        await add_pair(db, instruments, "QUIET", Resolution.MINUTE, LIMIT)


@respx.mock
@pytest.mark.db
async def test_a_gateway_that_is_down_is_not_a_refusal(
    db: asyncpg.Connection, instruments: GatewayInstruments
) -> None:
    # The pair was not rejected, it was never asked about. Retrying makes sense for this
    # and does not for a refusal, so they must not arrive as the same thing.
    respx.get(f"{BASE_URL}/instruments/US100/candles").mock(
        side_effect=httpx.ConnectError("connection refused")
    )

    with pytest.raises(GatewayUnreachable):
        await add_pair(db, instruments, "US100", Resolution.MINUTE, LIMIT)


@respx.mock
@pytest.mark.db
async def test_validation_happens_before_the_ceiling_is_spent(
    db: asyncpg.Connection, instruments: GatewayInstruments
) -> None:
    respx.get(f"{BASE_URL}/instruments/NOPE/candles").mock(
        return_value=httpx.Response(404, json={"detail": "unknown symbol"})
    )
    await track(db, "SYM0", Resolution.MINUTE, limit=2)

    with pytest.raises(UnknownPair):
        await add_pair(db, instruments, "NOPE", Resolution.MINUTE, limit=2)

    assert len(await read_tracked(db)) == 1


# --- collect_from: where history is meant to reach back to ---------------------------


def test_default_collect_from_is_default_bars_back() -> None:
    now = MOMENT
    result = default_collect_from(Resolution.MINUTE, 5000, now)
    assert result == now - timedelta(minutes=5000)


@pytest.mark.db
async def test_a_pair_tracked_without_a_moment_gets_the_default_depth(
    db: asyncpg.Connection,
) -> None:
    pair = await track(db, "US100", Resolution.MINUTE, LIMIT, default_bars=100)
    expected = default_collect_from(Resolution.MINUTE, 100, pair.added_at)
    assert abs((pair.collect_from - expected).total_seconds()) < 5


@pytest.mark.db
async def test_a_pair_tracked_with_an_explicit_moment_keeps_it(db: asyncpg.Connection) -> None:
    wanted = MOMENT - timedelta(days=365)
    pair = await track(db, "US100", Resolution.MINUTE, LIMIT, collect_from=wanted)
    assert pair.collect_from == wanted


@pytest.mark.db
async def test_re_tracking_with_an_earlier_moment_pulls_collect_from_back(
    db: asyncpg.Connection,
) -> None:
    await track(db, "US100", Resolution.MINUTE, LIMIT, collect_from=MOMENT - timedelta(days=30))
    earlier = MOMENT - timedelta(days=365)

    pair = await track(db, "US100", Resolution.MINUTE, LIMIT, collect_from=earlier)

    assert pair.collect_from == earlier


@pytest.mark.db
async def test_re_tracking_with_a_later_moment_does_not_abandon_history(
    db: asyncpg.Connection,
) -> None:
    # The archive already committed to reaching this far back; a later request must not
    # walk that commitment back.
    original = MOMENT - timedelta(days=365)
    await track(db, "US100", Resolution.MINUTE, LIMIT, collect_from=original)

    pair = await track(db, "US100", Resolution.MINUTE, LIMIT, collect_from=MOMENT - timedelta(days=30))

    assert pair.collect_from == original


@pytest.mark.db
async def test_status_carries_collect_from(db: asyncpg.Connection) -> None:
    wanted = MOMENT - timedelta(days=90)
    await track(db, "US100", Resolution.MINUTE, LIMIT, collect_from=wanted)

    [status] = await read_status(db, now=MOMENT)

    assert status.collect_from == wanted
