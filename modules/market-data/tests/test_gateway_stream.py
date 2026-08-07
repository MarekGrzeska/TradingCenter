from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import websockets

from market_data.errors import GatewayUnreachable, UnreadablePayload
from market_data.gateway import (
    CandleUpdate,
    FeedFailure,
    FeedState,
    FeedStatus,
    Quote,
    read_message,
    stream_url,
    subscribe,
)
from market_data.models import CandleSource, PriceSide, Resolution

MOMENT = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)
EPOCH_SECONDS = 1_786_104_000

CANDLE_FRAME = {
    "kind": "candle",
    "symbol": "US100",
    "resolution": "MINUTE_5",
    "time": EPOCH_SECONDS,
    "open": 100.0,
    "high": 101.0,
    "low": 99.0,
    "close": 100.5,
    "volume": None,
    "forming": True,
}
QUOTE_FRAME = {
    "kind": "quote",
    "symbol": "US100",
    "time": EPOCH_SECONDS * 1000 + 234,
    "bid": 100.4,
    "ask": 100.6,
}


# --- the subscription is the URL ----------------------------------------------------


def test_the_subscription_is_the_query_string() -> None:
    url = stream_url("ws://gateway.test:8010/ws/stream", "US100", Resolution.MINUTE_5)
    assert url == "ws://gateway.test:8010/ws/stream?symbol=US100&resolution=MINUTE_5"


def test_a_trailing_slash_does_not_make_a_second_path() -> None:
    url = stream_url("ws://gateway.test:8010/ws/stream/", "GOLD", Resolution.HOUR)
    assert url.startswith("ws://gateway.test:8010/ws/stream?")


# --- the four kinds (3.2) -----------------------------------------------------------


def test_a_candle_frame_becomes_a_candle() -> None:
    message = read_message(json.dumps(CANDLE_FRAME))

    assert isinstance(message, CandleUpdate)
    assert message.candle.symbol == "US100"
    assert message.candle.resolution is Resolution.MINUTE_5
    assert message.candle.period_start == MOMENT
    assert message.candle.close == 100.5
    assert message.candle.price_side is PriceSide.BID
    assert message.candle.source is CandleSource.STREAM


def test_the_forming_mark_is_carried_not_dropped() -> None:
    # The gateway sends one kind for both and marks which, because a chart upserts by
    # timestamp. The archive reads the mark and stores only what has closed.
    forming = read_message(json.dumps(CANDLE_FRAME))
    settled = read_message(json.dumps({**CANDLE_FRAME, "forming": False}))

    assert isinstance(forming, CandleUpdate) and forming.candle.forming is True
    assert isinstance(settled, CandleUpdate) and settled.candle.forming is False


def test_a_streamed_candle_has_no_volume() -> None:
    # Neither the provider's candle event nor its quotes carry volume. One more reason a
    # backfilled value outranks a streamed one for the same period.
    message = read_message(json.dumps(CANDLE_FRAME))
    assert isinstance(message, CandleUpdate)
    assert message.candle.volume is None


def test_a_quote_frame_becomes_a_quote_in_milliseconds() -> None:
    message = read_message(json.dumps(QUOTE_FRAME))

    assert isinstance(message, Quote)
    assert message.at == MOMENT.replace(microsecond=234_000)
    assert (message.bid, message.ask) == (100.4, 100.6)


@pytest.mark.parametrize(
    "state", ["connecting", "connected", "reconnecting", "closed"]
)
def test_every_feed_state_is_recognised(state: str) -> None:
    message = read_message(json.dumps({"kind": "status", "state": state}))
    assert isinstance(message, FeedStatus)
    assert message.state is FeedState(state)


def test_an_error_frame_is_read_not_raised() -> None:
    # The socket is still open and the next frame may well be a candle.
    message = read_message(json.dumps({"kind": "error", "message": "upstream dropped"}))
    assert isinstance(message, FeedFailure)
    assert message.message == "upstream dropped"


# --- what it refuses to guess at ----------------------------------------------------


def test_a_kind_this_module_does_not_consume_is_ignored() -> None:
    # The gateway adding a fifth message kind should not be an outage here.
    assert read_message(json.dumps({"kind": "orderbook", "levels": []})) is None


def test_a_frame_with_no_kind_is_ignored() -> None:
    assert read_message(json.dumps({"symbol": "US100"})) is None


def test_a_frame_that_is_not_json_names_itself() -> None:
    with pytest.raises(UnreadablePayload, match="not JSON"):
        read_message("<html>502 Bad Gateway</html>")


def test_a_frame_that_is_not_an_object_names_itself() -> None:
    with pytest.raises(UnreadablePayload, match="not an object"):
        read_message("[1, 2, 3]")


def test_a_candle_frame_missing_a_field_is_drift_not_silence() -> None:
    broken = {k: v for k, v in CANDLE_FRAME.items() if k != "close"}
    with pytest.raises(UnreadablePayload, match="candle"):
        read_message(json.dumps(broken))


def test_a_status_frame_with_an_unknown_state_is_drift() -> None:
    with pytest.raises(UnreadablePayload, match="status"):
        read_message(json.dumps({"kind": "status", "state": "havoc"}))


# --- against a real socket ----------------------------------------------------------


@pytest.fixture
async def gateway_feed() -> AsyncIterator[str]:
    """A stand-in for the gateway's `/ws/stream`, sending what its README documents."""
    sent = [
        {"kind": "status", "state": "connected"},
        CANDLE_FRAME,
        QUOTE_FRAME,
        {**CANDLE_FRAME, "forming": False},
        {"kind": "orderbook", "levels": []},
    ]

    async def handler(connection) -> None:
        for frame in sent:
            await connection.send(json.dumps(frame))
        await connection.close()

    async with websockets.serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        yield f"ws://127.0.0.1:{port}/ws/stream"


async def test_a_subscription_reads_the_feed_in_order(gateway_feed: str) -> None:
    async with subscribe(gateway_feed, "US100", Resolution.MINUTE_5) as messages:
        received = [message async for message in messages]

    # Five frames were sent; the orderbook is a kind this module does not consume.
    assert [type(m) for m in received] == [FeedStatus, CandleUpdate, Quote, CandleUpdate]
    assert received[1].candle.forming is True
    assert received[3].candle.forming is False


@pytest.fixture
async def idle_feed() -> AsyncIterator[tuple[str, asyncio.Event]]:
    """A feed that says one thing and then waits, so the client decides when it ends."""
    hung_up = asyncio.Event()

    async def handler(connection) -> None:
        await connection.send(json.dumps({"kind": "status", "state": "connected"}))
        try:
            await connection.wait_closed()
        finally:
            hung_up.set()

    async with websockets.serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        yield f"ws://127.0.0.1:{port}/ws/stream", hung_up


async def test_the_socket_closes_when_the_caller_is_done(
    idle_feed: tuple[str, asyncio.Event],
) -> None:
    # The gateway holds one provider connection per room and keeps it only while
    # somebody is listening, so a socket left open is a provider session spent on nobody.
    url, hung_up = idle_feed

    async with subscribe(url, "US100", Resolution.MINUTE_5) as messages:
        assert isinstance(await anext(messages), FeedStatus)
        assert not hung_up.is_set()

    await asyncio.wait_for(hung_up.wait(), timeout=5)


async def test_a_gateway_that_is_not_listening_is_named_as_unreachable() -> None:
    with pytest.raises(GatewayUnreachable, match="US100"):
        async with subscribe("ws://127.0.0.1:1/ws/stream", "US100", Resolution.MINUTE_5):
            pass
