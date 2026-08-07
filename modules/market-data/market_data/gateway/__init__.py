"""`capital-gateway`, as this module consumes it — and the only place that talks to it.

Two roads carry candles here: `/instruments/{symbol}/history` for depth and `/ws/stream`
for what is happening now. They spell a period start differently, so both go through
`market_data.periods` and arrive as the same instant.
"""

from .history import DEFAULT_TIMEOUT, GatewayHistory, HistoryPage, http_client
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
    "CandleUpdate",
    "FeedFailure",
    "FeedState",
    "FeedStatus",
    "GatewayHistory",
    "HistoryPage",
    "Quote",
    "StreamMessage",
    "http_client",
    "read_message",
    "stream_url",
    "subscribe",
]
