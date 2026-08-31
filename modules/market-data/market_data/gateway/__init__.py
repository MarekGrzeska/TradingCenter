"""`capital-gateway`, as this module consumes it — and the only place that talks to it. Both roads
that carry candles go through `market_data.periods` and arrive as the same instant."""

from ._http import DEFAULT_TIMEOUT, GATEWAY_KEY_HEADER, http_client
from .history import GatewayHistory, HistoryPage
from .instruments import GatewayInstruments
from .stream import (
    CandleUpdate,
    FeedFailure,
    FeedState,
    FeedStatus,
    Quote,
    StreamMessage,
    read_message,
    stream_url,
    subscribe,
)

__all__ = [
    "DEFAULT_TIMEOUT",
    "GATEWAY_KEY_HEADER",
    "CandleUpdate",
    "FeedFailure",
    "FeedState",
    "FeedStatus",
    "GatewayHistory",
    "GatewayInstruments",
    "HistoryPage",
    "Quote",
    "StreamMessage",
    "http_client",
    "read_message",
    "stream_url",
    "subscribe",
]
