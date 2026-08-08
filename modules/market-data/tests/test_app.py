from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from market_data.app import app, candle_sink
from market_data.config import Settings
from market_data.coverage import record_coverage
from market_data.hub import CandleChange, Hub, Snapshot
from market_data.models import Candle, CandleSource, Resolution
from market_data.rollups import refresh_all
from market_data.store import read_candles, write_candles
from market_data.tracking import track

pytestmark = pytest.mark.db

NOW = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)
LIMIT = 20


def candle(offset: int = 0, **overrides) -> Candle:
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
            "source": CandleSource.HISTORY,
            **overrides,
        }
    )


class FakeInstruments:
    def __init__(self, collectable: bool = True, error: Exception | None = None):
        self.collectable = collectable
        self.error = error

    async def is_collectable(self, symbol: str, resolution: Resolution) -> bool:
        if self.error is not None:
            raise self.error
        return self.collectable


class FakeIngest:
    """Stands in for the supervisor. The routes only ever ask it to reconcile."""

    def __init__(self) -> None:
        self.syncs = 0
        self.running: set = set()
        self.started_at = NOW

    async def sync(self) -> None:
        self.syncs += 1


@pytest.fixture
async def pool(migrated_url: str):
    from market_data.db import pool as make_pool

    async with make_pool(migrated_url, max_size=5) as created:
        async with created.acquire() as conn:
            await conn.execute("TRUNCATE candles, derived_candles, tracked_pairs, coverage_ranges")
        yield created


@pytest.fixture
async def api(pool, migrated_url: str):
    """The app wired to a real database, with the two things that reach outward faked.

    The lifespan is bypassed rather than run: it would start ingest, which would try to
    reach a gateway that is not there. What is under test here is the contract.
    """
    app.state.pool = pool
    app.state.hub = Hub()
    app.state.settings = Settings(database_url=migrated_url, _env_file=None)
    app.state.instruments = FakeInstruments()
    app.state.ingest = FakeIngest()

    # `raise_app_exceptions=False` so the app's own error handling is what the test sees.
    # With the default, the transport re-raises whatever the app raised and the 500 the
    # handler produced — the thing under test in 8.7 — never reaches the response.
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://archive.test") as client:
        yield client


# --- 8.1: reading a range ------------------------------------------------------------


async def test_a_range_read_answers_with_candles(api, pool) -> None:
    async with pool.acquire() as conn:
        await write_candles(conn, [candle(m) for m in range(3)])

    body = (await api.get("/candles/US100", params={"resolution": "MINUTE"})).json()

    assert [_at(c["time"]) for c in body["candles"]] == [
        NOW - timedelta(minutes=m) for m in (2, 1, 0)
    ]


async def test_the_answer_names_the_side_of_the_spread(api, pool) -> None:
    # Never inferred by a consumer. The archive holds bid, and a series quietly compared
    # against an ask-side one is off by a spread that looks like a real move.
    body = (await api.get("/candles/US100")).json()

    assert body["price_side"] == "bid"
    assert body["resolution"] == "MINUTE"


async def test_a_range_read_honours_its_bounds(api, pool) -> None:
    async with pool.acquire() as conn:
        await write_candles(conn, [candle(m) for m in range(5)])

    body = (
        await api.get(
            "/candles/US100",
            params={
                "from": (NOW - timedelta(minutes=3)).isoformat(),
                "to": (NOW - timedelta(minutes=1)).isoformat(),
            },
        )
    ).json()

    assert len(body["candles"]) == 2  # `to` is exclusive, so the minute at NOW-1 is out


async def test_a_derived_resolution_is_served_from_the_derivation(api, pool) -> None:
    async with pool.acquire() as conn:
        await write_candles(conn, [candle(m) for m in range(10)])
        await refresh_all(conn, "US100", NOW - timedelta(minutes=10), NOW)

    body = (await api.get("/candles/US100", params={"resolution": "MINUTE_5"})).json()

    assert body["derived"] is True
    assert body["candles"]


async def test_a_collected_resolution_says_it_was_not_derived(api, pool) -> None:
    body = (await api.get("/candles/US100", params={"resolution": "MINUTE"})).json()
    assert body["derived"] is False


async def test_a_range_that_ends_before_it_starts_is_refused_by_name(api) -> None:
    response = await api.get(
        "/candles/US100",
        params={"from": NOW.isoformat(), "to": (NOW - timedelta(hours=1)).isoformat()},
    )

    # A refusal, not a failure: the request is what is wrong, and a 500 would send a
    # caller looking for a fault in the archive.
    assert response.status_code == 422
    assert "is before" in response.json()["detail"]


# --- 8.2: saying which part was never collected --------------------------------------


async def test_a_range_read_marks_what_was_never_collected(api, pool) -> None:
    async with pool.acquire() as conn:
        await record_coverage(
            conn, "US100", Resolution.MINUTE, NOW - timedelta(minutes=10), NOW - timedelta(minutes=5)
        )

    body = (
        await api.get(
            "/candles/US100",
            params={"from": (NOW - timedelta(minutes=10)).isoformat(), "to": NOW.isoformat()},
        )
    ).json()

    [gap] = body["uncovered"]
    assert (_at(gap["from"]), _at(gap["to"])) == (NOW - timedelta(minutes=5), NOW)


async def test_a_fully_covered_range_marks_nothing(api, pool) -> None:
    # Which is not the same as the range being full of candles: a shut market is covered
    # and empty, and that is a complete answer.
    async with pool.acquire() as conn:
        await record_coverage(
            conn, "US100", Resolution.MINUTE, NOW - timedelta(hours=1), NOW + timedelta(hours=1)
        )

    body = (
        await api.get(
            "/candles/US100",
            params={"from": (NOW - timedelta(minutes=10)).isoformat(), "to": NOW.isoformat()},
        )
    ).json()

    assert body["uncovered"] == []


async def test_a_pair_never_collected_is_uncovered_end_to_end(api) -> None:
    body = (
        await api.get(
            "/candles/US100",
            params={"from": (NOW - timedelta(minutes=10)).isoformat(), "to": NOW.isoformat()},
        )
    ).json()

    assert body["candles"] == []
    assert len(body["uncovered"]) == 1


# --- 8.5: coverage ---------------------------------------------------------------------


async def test_coverage_reads_back_over_the_contract(api, pool) -> None:
    async with pool.acquire() as conn:
        await record_coverage(
            conn,
            "US100",
            Resolution.MINUTE,
            NOW - timedelta(hours=1),
            NOW,
            history_ended=True,
        )

    body = (await api.get("/coverage/US100")).json()

    [covered] = body["ranges"]
    assert (_at(covered["from"]), _at(covered["to"])) == (NOW - timedelta(hours=1), NOW)
    assert covered["history_ended"] is True
    assert _at(body["earliest_reachable"]) == NOW - timedelta(hours=1)


async def test_a_pair_with_no_coverage_says_so_without_failing(api) -> None:
    body = (await api.get("/coverage/GOLD")).json()

    assert body["ranges"] == []
    # Null means the end of provider history has not been reached, not that there is none.
    assert body["earliest_reachable"] is None


# --- 8.6: managing what is collected --------------------------------------------------


async def test_a_pair_can_be_taken_on_over_the_contract(api, pool) -> None:
    response = await api.post("/pairs", json={"symbol": "US100", "resolution": "MINUTE"})

    assert response.status_code == 201
    assert response.json()["symbol"] == "US100"
    assert [p["symbol"] for p in (await api.get("/pairs")).json()] == ["US100"]


async def test_taking_a_pair_on_starts_collecting_it_without_a_restart(api) -> None:
    await api.post("/pairs", json={"symbol": "US100", "resolution": "MINUTE"})

    assert app.state.ingest.syncs == 1


async def test_the_list_carries_how_collection_is_going(api, pool) -> None:
    async with pool.acquire() as conn:
        await track(conn, "US100", Resolution.MINUTE, LIMIT)
        await write_candles(conn, [candle(0)])

    [listed] = (await api.get("/pairs")).json()

    assert _at(listed["latest_candle"]) == NOW
    assert listed["collection"] in {"collecting", "stalled", "unknown"}


async def test_a_pair_can_be_let_go_over_the_contract(api, pool) -> None:
    async with pool.acquire() as conn:
        await track(conn, "US100", Resolution.MINUTE, LIMIT)
        await write_candles(conn, [candle(0)])

    response = await api.delete("/pairs/US100", params={"resolution": "MINUTE"})

    assert response.status_code == 204
    assert (await api.get("/pairs")).json() == []
    # The candles stay. An archive that deletes on a configuration change is not one.
    async with pool.acquire() as conn:
        assert len(await read_candles(conn, "US100", Resolution.MINUTE)) == 1


async def test_letting_go_of_a_pair_that_was_not_collected_is_a_404(api) -> None:
    response = await api.delete("/pairs/GOLD", params={"resolution": "MINUTE"})

    assert response.status_code == 404
    assert "not being collected" in response.json()["detail"]


# --- 8.7: refusals that name themselves -----------------------------------------------


async def test_going_over_the_ceiling_is_refused_with_the_reason(api, pool) -> None:
    app.state.settings = Settings(
        database_url="postgresql://u:p@h/d", max_tracked_pairs=1, _env_file=None
    )
    await api.post("/pairs", json={"symbol": "US100", "resolution": "MINUTE"})

    response = await api.post("/pairs", json={"symbol": "GOLD", "resolution": "MINUTE"})

    assert response.status_code == 409
    assert "ceiling of 1" in response.json()["detail"]


async def test_a_symbol_the_gateway_will_not_serve_is_refused_with_the_reason(api) -> None:
    app.state.instruments = FakeInstruments(collectable=False)

    response = await api.post("/pairs", json={"symbol": "NOPE", "resolution": "MINUTE"})

    assert response.status_code == 422
    assert "archive nothing" in response.json()["detail"]


async def test_a_gateway_that_is_down_is_reported_as_upstream(api) -> None:
    from market_data.errors import GatewayUnreachable

    app.state.instruments = FakeInstruments(error=GatewayUnreachable("connection refused"))

    response = await api.post("/pairs", json={"symbol": "US100", "resolution": "MINUTE"})

    # 504, not 500: the archive is fine and retrying it as though it were at fault is the
    # wrong response.
    assert response.status_code == 504


async def test_a_failure_never_carries_a_raw_database_error(api, pool) -> None:
    # A database message names tables and columns — more than a caller can use, and more
    # than should travel outward.
    await pool.close()

    response = await api.get("/candles/US100")

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert "see its logs" in detail
    for leak in ("asyncpg", "relation", "SELECT", "password", "candles"):
        assert leak not in detail


# --- 8.8: the schema describes the HTTP contract and nothing else ---------------------


async def test_the_websocket_path_is_absent_from_the_schema(api) -> None:
    """OpenAPI has no vocabulary for WebSocket payloads, so a path that appeared there
    would describe a contract it cannot actually state — and the README would become the
    second description rather than the only one."""
    schema = (await api.get("/openapi.json")).json()

    assert "/ws/candles" not in schema["paths"]
    assert not [path for path in schema["paths"] if path.startswith("/ws")]


async def test_the_http_routes_are_all_described(api) -> None:
    paths = (await api.get("/openapi.json")).json()["paths"]

    assert {"/candles/{symbol}", "/coverage/{symbol}", "/pairs", "/pairs/{symbol}"} <= set(paths)


async def test_the_schema_says_which_side_of_the_spread_is_stored(api) -> None:
    schema = (await api.get("/openapi.json")).json()

    assert "bid" in schema["info"]["description"]


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


# --- 8.9: subscribing to something nobody chose to collect -----------------------------


class FakeWebSocket:
    """Enough of a WebSocket to drive the handler's decisions.

    The handler is exercised directly rather than through a test client, because a client
    runs the app on its own event loop and the database pool belongs to this one.
    """

    def __init__(self, **params):
        self.query_params = params
        self.app = app
        self.accepted = False
        self.closed: tuple[int, str] | None = None
        self.sent: list[dict] = []

    async def accept(self) -> None:
        self.accepted = True

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed = (code, reason)

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)

    async def receive_text(self) -> str:
        from fastapi import WebSocketDisconnect

        raise WebSocketDisconnect(1000)


async def test_subscribing_to_a_pair_nobody_collects_is_refused(api, pool) -> None:
    """8.9. Subscribing must not quietly start collecting either — that is the decision
    the ceiling exists to keep deliberate."""
    from market_data.app import candle_feed

    socket = FakeWebSocket(symbol="US100", resolution="MINUTE")

    await candle_feed(socket, app.state.hub)

    assert socket.accepted is False
    assert socket.closed is not None
    assert "not being collected" in socket.closed[1]
    async with pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM tracked_pairs") == 0


async def test_subscribing_to_a_collected_pair_is_accepted(api, pool) -> None:
    from market_data.app import candle_feed

    async with pool.acquire() as conn:
        await track(conn, "US100", Resolution.MINUTE, LIMIT)
        await write_candles(conn, [candle(0)])
    socket = FakeWebSocket(symbol="US100", resolution="MINUTE")

    await candle_feed(socket, app.state.hub)

    assert socket.accepted is True
    assert socket.sent[0]["kind"] == "snapshot"
    assert len(socket.sent[0]["candles"]) == 1


async def test_a_subscription_is_accepted_through_the_router_too(api, pool) -> None:
    """The tests around this one call the handler themselves, which is how the handshake
    stayed broken while they all passed: the `hub` dependency asked for a `Request`, and a
    WebSocket connection is not one, so FastAPI had nothing to pass and every subscription
    failed with a 500 before the handler ran. Only the router can get that wrong, so only
    a connection made through it can notice."""
    async with pool.acquire() as conn:
        await track(conn, "US100", Resolution.MINUTE, LIMIT)
        await write_candles(conn, [candle(0)])

    sent = await _handshake("symbol=US100&resolution=MINUTE")

    assert sent[0]["type"] == "websocket.accept"
    assert json.loads(sent[1]["text"])["kind"] == "snapshot"


async def test_a_subscription_without_a_symbol_is_refused_before_the_handshake(api) -> None:
    from market_data.app import candle_feed

    socket = FakeWebSocket(resolution="MINUTE")

    await candle_feed(socket, app.state.hub)

    assert socket.accepted is False
    assert socket.closed[1] == "symbol is required"


async def test_a_subscription_with_an_unknown_resolution_is_refused(api) -> None:
    from market_data.app import candle_feed

    socket = FakeWebSocket(symbol="US100", resolution="MINUTE_2")

    await candle_feed(socket, app.state.hub)

    assert socket.accepted is False
    assert "unknown resolution" in socket.closed[1]


def _at(stamp: str) -> datetime:
    """The instant a timestamp names, however it was spelled.

    JSON renders UTC with a `Z`; comparing strings would be testing pydantic's choice of
    suffix rather than whether the archive answered with the right moment.
    """
    return datetime.fromisoformat(stamp)


async def _handshake(query: str) -> list[dict]:
    """Connect to /ws/candles through the app itself, and answer with what it sent back.

    httpx's ASGI transport speaks HTTP only, so the connection is made at the ASGI level:
    a connect, then a disconnect, which is enough to see how the handshake ended.
    """
    scope = {
        "type": "websocket",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "scheme": "ws",
        "path": "/ws/candles",
        "raw_path": b"/ws/candles",
        "query_string": query.encode(),
        "root_path": "",
        "headers": [(b"host", b"archive.test")],
        "client": ("127.0.0.1", 51234),
        "server": ("archive.test", 80),
        "subprotocols": [],
    }
    incoming = [{"type": "websocket.connect"}]
    sent: list[dict] = []

    async def receive() -> dict:
        return incoming.pop(0) if incoming else {"type": "websocket.disconnect", "code": 1000}

    async def send(message: dict) -> None:
        sent.append(message)

    await app(scope, receive, send)
    return sent


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
