"""Reading the gateway's live feed at `/ws/stream` — a reader, not a conversation. Reconnection is not
here: a dropped feed is also a gap to close, and deciding that needs the coverage ingest keeps."""

from __future__ import annotations

import asyncio
import json
import logging
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
from ._http import GATEWAY_KEY_HEADER

log = logging.getLogger(__name__)

# How long a subscription may deliver nothing before this module calls it over. Deliberately slower
# than the gateway's own watchdog, and counted from any frame: a DAY candle arrives once a day.
SILENCE_TOLERANCE_SECONDS = 20 * 60.0


class FeedState(str, Enum):
    """What the gateway says about its own connection to the provider. Carried through rather than
    collapsed into a boolean: "reconnecting" is a gap about to close itself, "closed" is not."""

    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    CLOSED = "closed"


class CandleUpdate(BaseModel):
    """A candle, forming or closed. The gateway sends one kind for both and marks which, because a
    chart upserts by timestamp; the archive reads the mark and stores only the closed ones."""

    kind: Literal["candle"] = "candle"
    candle: Candle


class Quote(BaseModel):
    """Bid and ask, about five a second. Not stored — orders of magnitude more data than candles —
    but read, because they move the forming candle and tell silence from a flat market."""

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
    """The subscription, which is the URL. A missing symbol or unknown resolution is refused before
    the handshake, so a bad one fails to connect rather than dying a moment later."""
    query = urlencode({"symbol": symbol, "resolution": resolution.value})
    return f"{base_url.rstrip('/')}?{query}"


def read_message(raw: str | bytes) -> StreamMessage | None:
    """One frame, read. `None` for a kind this module does not consume, so a fifth message kind is not
    an outage; `UnreadablePayload` for one it does, which is the two contracts having drifted."""
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
                # Always absent on this feed: neither the candle event nor the quotes carry volume.
                # A candle backfilled later may have it, one more reason history outranks a stream.
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


# `quote` is deliberately absent, and it is the busiest kind on the feed. Nothing here consumes one,
# so parsing them built hundreds of objects a second for the garbage collector.
_READERS = {
    "candle": _read_candle,
    "status": _read_status,
    "error": _read_error,
}


@asynccontextmanager
async def subscribe(
    base_url: str, symbol: str, resolution: Resolution, api_key: str
) -> AsyncIterator[AsyncIterator[StreamMessage]]:
    """One subscription, for as long as the socket lives. A context manager so the socket closes when
    the caller is done: the gateway holds a provider connection per room while somebody listens."""
    url = stream_url(base_url, symbol, resolution)
    try:
        # The key, and only the key. `/ws/stream` is excluded from the gateway's authenticator, which
        # intercepts an upgrade and never completes it — measured 20 August 2026, every feed dead.
        connection = await websockets.connect(
            url, additional_headers={GATEWAY_KEY_HEADER: api_key}
        )
    except (OSError, WebSocketException) as err:
        raise GatewayUnreachable(
            f"could not subscribe to {symbol} {resolution.value} at the gateway: {err}"
        ) from err

    async def messages() -> AsyncIterator[StreamMessage]:
        frames = connection.__aiter__()
        while True:
            try:
                frame = await asyncio.wait_for(
                    frames.__anext__(), SILENCE_TOLERANCE_SECONDS
                )
            except StopAsyncIteration:
                return
            except TimeoutError:
                log.warning(
                    "%s %s: the gateway sent nothing for %.0f minutes; ending the "
                    "subscription so it is opened again and the gap is closed",
                    symbol,
                    resolution.value,
                    SILENCE_TOLERANCE_SECONDS / 60,
                )
                return
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
