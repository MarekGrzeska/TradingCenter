"""What a subscriber receives — the WebSocket contract, since OpenAPI cannot describe it. The
provider's ``ohlc.event`` is not republished: it arrives once per price side, which makes a chart jump."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from ..dtos import Resolution


class CandleMessage(BaseModel):
    kind: Literal["candle"] = "candle"
    symbol: str
    resolution: Resolution
    # Seconds since the epoch, at the start of the candle's period. Seconds rather than the REST
    # side's ISO string because charting libraries index by it, and converting per tick is a cost.
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


# The four states a feed can be in, named once: the hub remembers the current one to greet a late
# subscriber with. Two spellings of the same set is how the pair drifts apart.
StreamState = Literal["connecting", "connected", "reconnecting", "closed"]


class StatusMessage(BaseModel):
    kind: Literal["status"] = "status"
    state: StreamState


class ErrorMessage(BaseModel):
    kind: Literal["error"] = "error"
    message: str


Message = CandleMessage | QuoteMessage | StatusMessage | ErrorMessage
