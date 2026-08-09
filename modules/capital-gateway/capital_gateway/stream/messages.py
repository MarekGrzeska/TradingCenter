"""What a subscriber receives. This is the WebSocket contract.

OpenAPI does not describe WebSocket payloads, so these models are the published shape —
they exist to be serialised and to be read, not merely to be convenient inside the hub.

Four kinds, and the split is deliberate:

``candle``  what a chart consumes. One kind for both the bar in progress and the sealed
            one, distinguished by ``forming``, because a chart library upserts by
            timestamp and does not want two message types to reconcile.
``quote``   raw bid and ask, about five a second. Kept alongside candles because a
            spread is needed at execution time and cannot wait for a candle to close.
``status``  whether the feed is live, so silence is distinguishable from a flat market.
``error``   what failed, never carrying a credential.

The provider's own ``ohlc.event`` is deliberately not republished: it arrives twice per
candle, once per price side, and forwarding both is what makes a chart jump across the
spread.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from ..dtos import Resolution


class CandleMessage(BaseModel):
    kind: Literal["candle"] = "candle"
    symbol: str
    resolution: Resolution
    # Seconds since the epoch, at the start of the candle's period. Seconds rather than
    # the ISO string the REST side uses because this is what charting libraries index
    # by, and converting per tick is the consumer's cost otherwise.
    time: int
    open: float
    high: float
    low: float
    close: float
    # Always None on this feed: neither the provider's candle event nor its quotes carry
    # volume. Present so the shape matches the REST candle rather than quietly differing.
    volume: float | None = None
    forming: bool


class QuoteMessage(BaseModel):
    kind: Literal["quote"] = "quote"
    symbol: str
    time: int  # milliseconds, as the provider sends it
    bid: float
    ask: float


# The four states a feed can be in, named once: the hub remembers the current one to
# greet a late subscriber with, and this message publishes it. Two spellings of the same
# set is how the pair drifts apart.
StreamState = Literal["connecting", "connected", "reconnecting", "closed"]


class StatusMessage(BaseModel):
    kind: Literal["status"] = "status"
    state: StreamState


class ErrorMessage(BaseModel):
    kind: Literal["error"] = "error"
    message: str


Message = CandleMessage | QuoteMessage | StatusMessage | ErrorMessage
