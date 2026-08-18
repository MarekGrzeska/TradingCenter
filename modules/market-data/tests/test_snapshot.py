"""The snapshot and what follows it, and the period still being built.

`market-data-api` 8.3, 8.4 and 8.10. The property under test throughout is the seam:
the snapshot is read while the room is held still and the subscriber attaches before it
is released, so no candle falls between the two and none arrives twice.

The forming candle is the other half — published, never stored.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
from fakes import (
    LIMIT,
    NOW,
    FakeInstruments,
    candle,
)

from market_data.app import candle_sink
from market_data.hub import CandleChange, Hub, Snapshot
from market_data.models import CandleSource, Resolution
from market_data.store import read_candles, write_candles
from market_data.tracking import track

pytestmark = pytest.mark.db


# --- 8.3, 8.4 and 8.10: the snapshot and what follows it -------------------------------


async def test_a_subscriber_is_handed_the_settled_series_first(pool) -> None:
    hub = Hub()
    async with pool.acquire() as conn:
        await write_candles(conn, [candle(m) for m in range(3)])
    received, collect = _collector()

    await hub.subscribe("US100", Resolution.MINUTE, collect, _settled(pool))

    [snapshot] = received
    assert isinstance(snapshot, Snapshot)
    assert [c.period_start for c in snapshot.candles] == [
        NOW - timedelta(minutes=m) for m in (2, 1, 0)
    ]


async def test_the_snapshot_carries_the_period_still_being_built(pool) -> None:
    # A chart joining midway would otherwise be missing the bar the price is actually in.
    hub = Hub()
    forming = candle(0, source=CandleSource.STREAM, forming=True)
    await hub.publish("US100", Resolution.MINUTE, forming)
    received, collect = _collector()

    await hub.subscribe("US100", Resolution.MINUTE, collect, _settled(pool))

    assert received[0].forming is not None
    assert received[0].forming.period_start == forming.period_start


async def test_a_closed_candle_clears_the_forming_one(pool) -> None:
    hub = Hub()
    await hub.publish("US100", Resolution.MINUTE, candle(0, forming=True))
    await hub.publish("US100", Resolution.MINUTE, candle(0, forming=False))
    received, collect = _collector()

    await hub.subscribe("US100", Resolution.MINUTE, collect, _settled(pool))

    assert received[0].forming is None


async def test_changes_after_the_snapshot_say_whether_a_candle_has_closed(pool) -> None:
    """8.4."""
    hub = Hub()
    received, collect = _collector()
    await hub.subscribe("US100", Resolution.MINUTE, collect, _settled(pool))

    await hub.publish("US100", Resolution.MINUTE, candle(0, forming=True))
    await hub.publish("US100", Resolution.MINUTE, candle(0, forming=False))

    changes = [m for m in received if isinstance(m, CandleChange)]
    assert [c.candle.forming for c in changes] == [True, False]


async def test_a_period_never_arrives_both_in_the_snapshot_and_after_it(
    pool, monkeypatch
) -> None:
    """8.10, and the reason the hold exists.

    Ingest stores a candle and then publishes it. If the store can commit outside the
    hold, there is a moment between the two where a subscriber's snapshot query sees the
    candle *and* the change carrying it is still to come — two bars for one period, on
    every chart that happened to connect just then.

    That moment is opened deliberately here rather than hoped for. Racing two tasks and
    trusting the scheduler to hit a window a few microseconds wide is how a test comes to
    pass against an implementation that has no hold at all, which this one did before it
    was written this way.
    """
    import market_data.app as app_module

    hub = Hub()
    committed = asyncio.Event()
    may_finish = asyncio.Event()
    real_store = app_module.store_closed_candle

    async def store_then_wait(pool_, stored_candle) -> None:
        await real_store(pool_, stored_candle)
        committed.set()
        await may_finish.wait()

    monkeypatch.setattr(app_module, "store_closed_candle", store_then_wait)

    sink = candle_sink(pool, hub)
    received, collect = _collector()

    producing = asyncio.create_task(sink(candle(0, source=CandleSource.STREAM)))
    await committed.wait()

    # The candle is now in the database and has not been broadcast. A subscriber attaching
    # at this instant is the whole hazard.
    attaching = asyncio.create_task(
        hub.subscribe("US100", Resolution.MINUTE, collect, _settled(pool))
    )
    await asyncio.sleep(0.05)  # every chance to slip in, if it can
    may_finish.set()
    await producing
    await attaching

    seen = [c.period_start for c in received[0].candles]
    seen += [m.candle.period_start for m in received[1:] if isinstance(m, CandleChange)]

    assert len(seen) == len(set(seen)), "a period arrived twice across the seam"
    assert len(seen) == 1


async def test_no_period_falls_between_the_snapshot_and_the_changes(pool) -> None:
    # The other half of the same guarantee: nothing may be missing either. A hundred
    # candles stored and published while a subscriber attaches somewhere in the middle.
    hub = Hub()
    sink = candle_sink(pool, hub)
    received, collect = _collector()

    async def produce():
        for m in range(100, 0, -1):
            await sink(candle(m, source=CandleSource.STREAM))

    async def attach():
        await asyncio.sleep(0)
        await hub.subscribe("US100", Resolution.MINUTE, collect, _settled(pool))

    await asyncio.gather(produce(), attach())

    seen = {c.period_start for c in received[0].candles}
    seen |= {m.candle.period_start for m in received[1:] if isinstance(m, CandleChange)}
    async with pool.acquire() as conn:
        stored = {c.period_start for c in await read_candles(conn, "US100", Resolution.MINUTE)}

    assert stored <= seen, "a candle was stored that the subscriber never learned about"


async def test_a_subscriber_that_fails_does_not_take_the_others_with_it(pool) -> None:
    # A socket that dies *after* subscribing, which is the case that happens: a failure
    # during the snapshot is the subscriber's own problem and is left to propagate, but
    # one during a broadcast must cost only that subscriber.
    hub = Hub()
    good, collect_good = _collector()
    sent = 0

    async def dies_after_the_snapshot(_message):
        nonlocal sent
        sent += 1
        if sent > 1:
            raise RuntimeError("this socket is gone")

    await hub.subscribe("US100", Resolution.MINUTE, collect_good, _settled(pool))
    await hub.subscribe("US100", Resolution.MINUTE, dies_after_the_snapshot, _settled(pool))
    assert hub.subscriber_count("US100", Resolution.MINUTE) == 2

    await hub.publish("US100", Resolution.MINUTE, candle(0))

    assert any(isinstance(m, CandleChange) for m in good)
    assert hub.subscriber_count("US100", Resolution.MINUTE) == 1


async def test_a_subscriber_stops_receiving_once_it_leaves(pool) -> None:
    hub = Hub()
    received, collect = _collector()
    await hub.subscribe("US100", Resolution.MINUTE, collect, _settled(pool))

    await hub.unsubscribe("US100", Resolution.MINUTE, collect)
    await hub.publish("US100", Resolution.MINUTE, candle(0))

    assert not [m for m in received if isinstance(m, CandleChange)]


# --- reading the period being built, without subscribing to it -------------------------
#
# specs/market-data-api, "Świeca w budowie jest oznaczona". The candle is the hub's, so
# these tests put one there the way ingest does — `hub.publish` with `forming=True` — and
# then read it over HTTP.


async def _tracked(pool, *resolutions: Resolution) -> None:
    async with pool.acquire() as conn:
        for resolution in resolutions:
            await track(conn, "US100", resolution, LIMIT)


async def test_the_forming_candle_is_readable_without_a_subscription(app, api, pool) -> None:
    await _tracked(pool, Resolution.MINUTE)
    await app.state.hub.publish("US100", Resolution.MINUTE, candle(0, forming=True, close=101.25))

    body = (await api.get("/candles/US100/forming")).json()

    assert body["state"] == "forming"
    assert body["resolution"] == "MINUTE"
    assert body["candle"]["close"] == 101.25
    assert body["price_side"] == "bid"


async def test_without_a_resolution_the_archive_answers_from_the_finest_live_one(app, 
    api, pool
) -> None:
    await _tracked(pool, Resolution.MINUTE, Resolution.HOUR)
    await app.state.hub.publish(
        "US100", Resolution.HOUR, candle(0, resolution=Resolution.HOUR, forming=True, close=200.0)
    )
    await app.state.hub.publish("US100", Resolution.MINUTE, candle(0, forming=True, close=101.0))

    body = (await api.get("/candles/US100/forming")).json()

    assert body["resolution"] == "MINUTE"
    assert body["candle"]["close"] == 101.0


async def test_a_stalled_finer_feed_does_not_hide_a_coarser_price(app, api, pool) -> None:
    """The reason the pick is "finest that has one" rather than "finest tracked". A pair
    tracked at MINUTE and HOUR whose minute feed has stopped still has a price."""
    await _tracked(pool, Resolution.MINUTE, Resolution.HOUR)
    await app.state.hub.publish(
        "US100", Resolution.HOUR, candle(0, resolution=Resolution.HOUR, forming=True, close=200.0)
    )

    body = (await api.get("/candles/US100/forming")).json()

    assert body["resolution"] == "HOUR"
    assert body["candle"]["close"] == 200.0


async def test_a_named_resolution_is_honoured_over_the_finer_one(app, api, pool) -> None:
    await _tracked(pool, Resolution.MINUTE, Resolution.HOUR)
    await app.state.hub.publish("US100", Resolution.MINUTE, candle(0, forming=True, close=101.0))
    await app.state.hub.publish(
        "US100", Resolution.HOUR, candle(0, resolution=Resolution.HOUR, forming=True, close=200.0)
    )

    body = (await api.get("/candles/US100/forming", params={"resolution": "HOUR"})).json()

    assert body["resolution"] == "HOUR"
    assert body["candle"]["close"] == 200.0


async def test_a_shut_market_says_so_rather_than_reading_as_missing_data(app, api, pool) -> None:
    await _tracked(pool, Resolution.MINUTE)
    app.state.instruments = FakeInstruments(market_open=False)

    body = (await api.get("/candles/US100/forming")).json()

    assert body["state"] == "market_closed"
    assert body["market_open"] is False
    assert body["candle"] is None


async def test_an_open_market_with_nothing_arriving_is_a_collection_failure(app, api, pool) -> None:
    # The one empty answer that needs somebody to go and look, and the one that would
    # otherwise be indistinguishable from a quiet weekend.
    await _tracked(pool, Resolution.MINUTE)
    app.state.instruments = FakeInstruments(market_open=True)

    body = (await api.get("/candles/US100/forming")).json()

    assert body["state"] == "no_quotes"
    assert body["market_open"] is True


async def test_a_gateway_that_will_not_answer_is_not_a_shut_market(app, api, pool) -> None:
    await _tracked(pool, Resolution.MINUTE)
    app.state.instruments = FakeInstruments(market_open=None)

    body = (await api.get("/candles/US100/forming")).json()

    # Claiming a closed market on the strength of an unanswered question is the one wrong
    # answer here that would read as certain.
    assert body["state"] == "no_quotes"
    assert body["market_open"] is None


async def test_an_untracked_symbol_says_nobody_collects_it(api) -> None:
    body = (await api.get("/candles/GOLD/forming")).json()

    assert body["state"] == "not_tracked"
    assert body["candle"] is None


async def test_reading_the_forming_candle_stores_nothing(app, api, pool) -> None:
    await _tracked(pool, Resolution.MINUTE)
    await app.state.hub.publish("US100", Resolution.MINUTE, candle(0, forming=True))

    await api.get("/candles/US100/forming")

    async with pool.acquire() as conn:
        stored = await read_candles(
            conn, "US100", Resolution.MINUTE, NOW - timedelta(hours=1), NOW + timedelta(hours=1)
        )
    assert stored == []


async def test_reading_does_not_leave_a_room_behind(app, api) -> None:
    """A read that created rooms would leave one per symbol anybody ever asked about, and
    `unsubscribe` only collects rooms it finds — one nobody subscribed to is never
    reached."""
    before = app.state.hub.room_count()

    await api.get("/candles/GOLD/forming")
    await api.get("/candles/SILVER/forming", params={"resolution": "MINUTE"})

    assert app.state.hub.room_count() == before




def _collector():
    """Subscribers are awaited, so `list.append` will not do."""
    received: list = []

    async def collect(message) -> None:
        received.append(message)

    return received, collect


def _settled(pool):
    async def read_settled():
        async with pool.acquire() as conn:
            from market_data.store import read_recent

            return list(await read_recent(conn, "US100", Resolution.MINUTE, 500))

    return read_settled
