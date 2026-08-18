"""Reading the gateway's live feed at `/ws/stream`.

There is no client protocol to get wrong: the subscription is the query string, and the
gateway reads nothing back. So this is a reader, not a conversation — connect, and take
the four kinds of message it sends.

Reconnection is not here. A dropped feed is not only a socket to reopen, it is a gap in
the archive to close, and deciding that needs the coverage the ingest side keeps. This
module hands up a clean stream and lets it end.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from enum import Enum
from typing import Literal
from urllib.parse import urlencode

import websockets
from pydantic import BaseModel, ValidationError
from websockets.exceptions import WebSocketException

from ..errors import GatewayUnreachable, UnreadablePayload
from ..models import Candle, CandleSource, PriceSide, Resolution
from ..periods import from_epoch_millis, from_epoch_seconds
from .history import GATEWAY_KEY_HEADER


class FeedState(str, Enum):
    """What the gateway says about its own connection to the provider.

    Carried through rather than collapsed into a boolean, because "reconnecting" and
    "closed" call for different answers: one is a gap that is about to close itself, the
    other is a gap that will not.
    """

    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    CLOSED = "closed"


class CandleUpdate(BaseModel):
    """A candle, forming or closed. The gateway sends one kind for both and marks which,
    because a chart upserts by timestamp; the archive reads the mark and stores only the
    closed ones."""

    kind: Literal["candle"] = "candle"
    candle: Candle


class Quote(BaseModel):
    """Bid and ask, about five a second.

    Not stored — quotes are two to three orders of magnitude more data than candles and
    nothing needs them yet — but read, because they are how the gateway's forming candle
    moves and how silence is told from a flat market.
    """

    kind: Literal["quote"] = "quote"
    symbol: str
    at: datetime
    bid: float
    ask: float


class FeedStatus(BaseModel):
    kind: Literal["status"] = "status"
    state: FeedState


class FeedFailure(BaseModel):
    """The gateway reporting its own failure. Not an exception here: the socket is still
    open and the next message may well be a candle."""

    kind: Literal["error"] = "error"
    message: str


StreamMessage = CandleUpdate | Quote | FeedStatus | FeedFailure


def stream_url(base_url: str, symbol: str, resolution: Resolution) -> str:
    """The subscription, which is the URL. A missing symbol or an unknown resolution is
    refused by the gateway before the handshake, so a bad one fails to connect rather
    than handing back a socket that dies a moment later."""
    query = urlencode({"symbol": symbol, "resolution": resolution.value})
    return f"{base_url.rstrip('/')}?{query}"


def read_message(raw: str | bytes) -> StreamMessage | None:
    """One frame, read.

    Returns `None` for a kind this module does not consume, so that the gateway adding a
    fifth message kind is not an outage here. Raises `UnreadablePayload` for a kind it
    does consume that does not match its published shape — that is the two modules'
    contract having drifted, and swallowing it would turn a broken feed into a quiet one.
    """
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as err:
        raise UnreadablePayload(f"the gateway sent a frame that is not JSON: {err}") from err

    if not isinstance(payload, dict):
        raise UnreadablePayload(f"the gateway sent a frame that is not an object: {payload!r}")

    kind = payload.get("kind")
    if kind not in _READERS:
        return None

    try:
        return _READERS[kind](payload)
    except (ValidationError, ValueError, KeyError, TypeError) as err:
        raise UnreadablePayload(
            f"the gateway sent a {kind!r} frame this module cannot read: {err}"
        ) from err


def _read_candle(payload: dict) -> CandleUpdate:
    message = _CandleMessage.model_validate(payload)
    return CandleUpdate(
        candle=Candle(
            symbol=message.symbol,
            resolution=message.resolution,
            period_start=from_epoch_seconds(message.time),
            open=message.open,
            high=message.high,
            low=message.low,
            close=message.close,
            # Always absent on this feed: neither the provider's candle event nor its
            # quotes carry volume. A candle backfilled later may have it, which is one
            # more reason a history value outranks a streamed one for the same period.
            volume=message.volume,
            price_side=PriceSide.BID,
            source=CandleSource.STREAM,
            forming=message.forming,
        )
    )


def _read_quote(payload: dict) -> Quote:
    message = _QuoteMessage.model_validate(payload)
    return Quote(
        symbol=message.symbol,
        at=from_epoch_millis(message.time),
        bid=message.bid,
        ask=message.ask,
    )


def _read_status(payload: dict) -> FeedStatus:
    return FeedStatus(state=FeedState(payload["state"]))


def _read_error(payload: dict) -> FeedFailure:
    return FeedFailure(message=str(payload["message"]))


# `quote` is deliberately absent, and it is the busiest kind on the feed: about five a
# second per pair, times the pairs this module tracks. Nothing here consumes one —
# `ingest/live.py`'s listener has a branch for a candle, a status and a failure, and none
# for a quote — so parsing them built hundreds of objects a second for the garbage
# collector. `read_message` answers `None` for a kind this module does not consume, which
# is the same thing it already did for the orderbook.
#
# `_read_quote` and `Quote` stay: they describe a frame the gateway still sends, and the
# reader is one line from being wanted again the day something here needs a tick.
_READERS = {
    "candle": _read_candle,
    "status": _read_status,
    "error": _read_error,
}


@asynccontextmanager
async def subscribe(
    base_url: str, symbol: str, resolution: Resolution, api_key: str
) -> AsyncIterator[AsyncIterator[StreamMessage]]:
    """One subscription, for as long as the socket lives.

    A context manager rather than a bare generator so the socket closes when the caller
    is done with it — the gateway holds one provider connection per room and keeps it
    only while somebody is listening, so a socket left open is a provider session spent
    on nobody.
    """
    url = stream_url(base_url, symbol, resolution)
    try:
        connection = await websockets.connect(
            url, additional_headers={GATEWAY_KEY_HEADER: api_key}
        )
    except (OSError, WebSocketException) as err:
        raise GatewayUnreachable(
            f"could not subscribe to {symbol} {resolution.value} at the gateway: {err}"
        ) from err

    async def messages() -> AsyncIterator[StreamMessage]:
        async for frame in connection:
            message = read_message(frame)
            if message is not None:
                yield message

    try:
        yield messages()
    finally:
        await connection.close()


class _CandleMessage(BaseModel):
    symbol: str
    resolution: Resolution
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    forming: bool


class _QuoteMessage(BaseModel):
    symbol: str
    time: int
    bid: float
    ask: float
