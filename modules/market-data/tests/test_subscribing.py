"""Who may subscribe, and how a browser gets in. `/ws/candles` is the one path outside Easy Auth, so
the ticket is the whole of what stands between the internet and the stream."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta

import pytest
from fakes import (
    LIMIT,
    candle,
)

from market_data.models import Resolution
from market_data.store import write_candles
from market_data.tickets import TicketStore
from market_data.tracking import track

pytestmark = pytest.mark.db



class FakeWebSocket:
    """Enough of a WebSocket to drive the handler's decisions. The handler is exercised directly rather
    than through a test client, because a client runs the app on its own event loop."""

    def __init__(self, app, **params):
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


def a_ticket(app) -> str:
    """A live ticket, from the store the app is actually running with. Spelled out at every call site,
    because a default would mean no test could tell whether the guard was there at all."""
    return app.state.tickets.issue("test-principal").value


async def test_subscribing_to_a_pair_nobody_collects_is_refused(app, api, pool) -> None:
    """8.9. Subscribing must not quietly start collecting either — that is the decision
    the ceiling exists to keep deliberate."""
    from market_data.routers.stream import candle_feed

    socket = FakeWebSocket(app, symbol="US100", resolution="MINUTE", ticket=a_ticket(app))

    await candle_feed(socket, app.state.hub)

    assert socket.accepted is False
    assert socket.closed is not None
    assert "not being collected" in socket.closed[1]
    async with pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM tracked_pairs") == 0


async def test_subscribing_to_a_collected_pair_is_accepted(app, api, pool) -> None:
    from market_data.routers.stream import candle_feed

    async with pool.acquire() as conn:
        await track(conn, "US100", Resolution.MINUTE, LIMIT)
        await write_candles(conn, [candle(0)])
    socket = FakeWebSocket(app, symbol="US100", resolution="MINUTE", ticket=a_ticket(app))

    await candle_feed(socket, app.state.hub)

    assert socket.accepted is True
    assert socket.sent[0]["kind"] == "snapshot"
    assert len(socket.sent[0]["candles"]) == 1


async def test_a_subscription_is_accepted_through_the_router_too(app, api, pool) -> None:
    """The tests around this one call the handler themselves, which is how the handshake stayed broken
    while they all passed: the `hub` dependency asked for a `Request`, which a WebSocket is not."""
    async with pool.acquire() as conn:
        await track(conn, "US100", Resolution.MINUTE, LIMIT)
        await write_candles(conn, [candle(0)])

    sent = await _handshake(app, f"symbol=US100&resolution=MINUTE&ticket={a_ticket(app)}")

    assert sent[0]["type"] == "websocket.accept"
    assert json.loads(sent[1]["text"])["kind"] == "snapshot"


async def test_a_subscription_without_a_symbol_is_refused_before_the_handshake(app, api) -> None:
    from market_data.routers.stream import candle_feed

    socket = FakeWebSocket(app, resolution="MINUTE", ticket=a_ticket(app))

    await candle_feed(socket, app.state.hub)

    assert socket.accepted is False
    assert socket.closed[1] == "symbol is required"


async def test_a_subscription_with_an_unknown_resolution_is_refused(app, api) -> None:
    from market_data.routers.stream import candle_feed

    socket = FakeWebSocket(app, symbol="US100", resolution="MINUTE_2", ticket=a_ticket(app))

    await candle_feed(socket, app.state.hub)

    assert socket.accepted is False
    assert "unknown resolution" in socket.closed[1]



async def test_a_ticket_is_issued_with_the_time_it_stays_good_for(api) -> None:
    response = await api.post("/stream-tickets")

    assert response.status_code == 200
    body = response.json()
    assert body["ticket"]
    assert body["expires_in_seconds"] == 30


async def test_a_ticket_records_the_principal_the_platform_identified(app, api) -> None:
    await api.post("/stream-tickets", headers={"X-MS-CLIENT-PRINCIPAL-ID": "operator-object-id"})

    (ticket,) = app.state.tickets._issued.values()
    assert ticket.issued_to == "operator-object-id"


async def test_a_ticket_is_refused_when_the_platform_identified_nobody(app, api) -> None:
    """The module does not take it on trust that the layer in front is doing its job: configured to stand
    behind one, a request with no identity means that layer is not there."""
    app.state.settings = app.state.settings.model_copy(
        update={"require_authenticated_principal": True}
    )

    response = await api.post("/stream-tickets")

    assert response.status_code == 401
    assert len(app.state.tickets) == 0


async def test_a_ticket_is_issued_without_a_principal_when_nothing_stands_in_front(app, api) -> None:
    """Local development: nothing is in front, so there is no identity to have — and the
    handshake still demands a ticket, so it is the same code path either way."""
    assert app.state.settings.require_authenticated_principal is False

    response = await api.post("/stream-tickets")

    assert response.status_code == 200


async def test_the_ticket_route_is_not_under_the_path_exempted_from_easy_auth(api) -> None:
    """`infra/app-service.tf` exempts `/ws/candles` from Easy Auth because a browser cannot authenticate
    a handshake. A ticket factory sharing that prefix would be one careless match from being exempt."""
    schema = (await api.get("/openapi.json")).json()

    assert "/stream-tickets" in schema["paths"]
    assert not any(path.startswith("/ws") for path in schema["paths"])


async def test_a_handshake_without_a_ticket_is_refused(app, api, pool) -> None:
    from market_data.routers.stream import candle_feed

    async with pool.acquire() as conn:
        await track(conn, "US100", Resolution.MINUTE, LIMIT)
    socket = FakeWebSocket(app, symbol="US100", resolution="MINUTE")

    await candle_feed(socket, app.state.hub)

    assert socket.accepted is False
    assert "ticket" in socket.closed[1]


async def test_a_handshake_with_a_ticket_the_archive_never_issued_is_refused(app, api) -> None:
    from market_data.routers.stream import candle_feed

    socket = FakeWebSocket(app, symbol="US100", resolution="MINUTE", ticket="not-one-of-ours")

    await candle_feed(socket, app.state.hub)

    assert socket.accepted is False
    assert "ticket" in socket.closed[1]


async def test_a_ticket_works_once_and_the_first_connection_survives_the_second_try(app, 
    api, pool
) -> None:
    from market_data.routers.stream import candle_feed

    async with pool.acquire() as conn:
        await track(conn, "US100", Resolution.MINUTE, LIMIT)
        await write_candles(conn, [candle(0)])
    ticket = a_ticket(app)

    first = FakeWebSocket(app, symbol="US100", resolution="MINUTE", ticket=ticket)
    await candle_feed(first, app.state.hub)
    second = FakeWebSocket(app, symbol="US100", resolution="MINUTE", ticket=ticket)
    await candle_feed(second, app.state.hub)

    assert first.accepted is True
    assert first.closed is None, "the second attempt must not disturb the connection it copies"
    assert second.accepted is False
    assert "ticket" in second.closed[1]


async def test_a_handshake_with_an_expired_ticket_is_refused(app, api, pool) -> None:
    from market_data.routers.stream import candle_feed

    clock = [datetime(2026, 8, 9, 12, 0, tzinfo=UTC)]
    app.state.tickets = TicketStore(timedelta(seconds=30), now=lambda: clock[0])
    ticket = app.state.tickets.issue("test-principal").value
    clock[0] += timedelta(seconds=31)
    async with pool.acquire() as conn:
        await track(conn, "US100", Resolution.MINUTE, LIMIT)

    socket = FakeWebSocket(app, symbol="US100", resolution="MINUTE", ticket=ticket)
    await candle_feed(socket, app.state.hub)

    assert socket.accepted is False
    assert "ticket" in socket.closed[1]


async def test_the_two_reasons_a_handshake_is_refused_are_told_apart(app, api, pool) -> None:
    """One is fixed by authenticating again, the other only by collecting the pair. A
    consumer that cannot tell them apart retries the wrong one forever."""
    from market_data.routers.stream import candle_feed

    async with pool.acquire() as conn:
        await track(conn, "US100", Resolution.MINUTE, LIMIT)

    no_ticket = FakeWebSocket(app, symbol="US100", resolution="MINUTE")
    await candle_feed(no_ticket, app.state.hub)
    untracked = FakeWebSocket(app, symbol="EURUSD", resolution="MINUTE", ticket=a_ticket(app))
    await candle_feed(untracked, app.state.hub)

    assert no_ticket.closed[1] != untracked.closed[1]
    assert "ticket" in no_ticket.closed[1]
    assert "not being collected" in untracked.closed[1]


async def test_no_ticket_value_reaches_the_logs(app, api, pool, caplog) -> None:
    from market_data.routers.stream import candle_feed

    async with pool.acquire() as conn:
        await track(conn, "US100", Resolution.MINUTE, LIMIT)
        await write_candles(conn, [candle(0)])

    with caplog.at_level(logging.INFO, logger="market_data.routers.stream"):
        issued = (
            await api.post(
                "/stream-tickets", headers={"X-MS-CLIENT-PRINCIPAL-ID": "operator-object-id"}
            )
        ).json()["ticket"]
        accepted = FakeWebSocket(app, symbol="US100", resolution="MINUTE", ticket=issued)
        await candle_feed(accepted, app.state.hub)
        refused = FakeWebSocket(app, symbol="US100", resolution="MINUTE", ticket=issued)
        await candle_feed(refused, app.state.hub)

    assert accepted.accepted is True
    assert refused.accepted is False
    assert issued not in caplog.text
    # The fact is worth having; the value never is.
    assert "stream ticket issued to operator-object-id" in caplog.text
    assert "no valid ticket" in caplog.text




async def _handshake(app, query: str) -> list[dict]:
    """Connect to /ws/candles through the app itself, and answer with what it sent back. httpx's ASGI
    transport speaks HTTP only, so the connection is made at the ASGI level."""
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
