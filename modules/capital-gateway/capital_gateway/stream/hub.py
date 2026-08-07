"""Rooms: who is listening to what, and the one connection each room shares.

The sharing is the point. Ten browser tabs on the same instrument are ten subscribers
and one connection to capital.com — the provider limits how many a session may hold, and
opening one per subscriber spends that limit on duplicate data.

This is also where a provider event becomes a published message: the upstream emits
sealed candles and quotes, the room folds them through its forming candle, and what
leaves is the contract in ``messages``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from ..dtos import Resolution
from .forming import Bar, FormingCandle
from .messages import CandleMessage, ErrorMessage, Message, QuoteMessage, StatusMessage
from .upstream import Upstream

Subscriber = Callable[[Message], Awaitable[None]]
UpstreamFactory = Callable[[str, Resolution, Callable[[dict], Awaitable[None]]], Upstream]


class Room:
    def __init__(self, epic: str, resolution: Resolution) -> None:
        self.epic = epic
        self.resolution = resolution
        self.subscribers: set[Subscriber] = set()
        self.forming = FormingCandle(resolution)
        self.upstream: Upstream | None = None
        # Remembered so a subscriber joining a live room is told the feed is up rather
        # than waiting in silence for the next provider event.
        self.state: str = "connecting"

    async def broadcast(self, message: Message) -> None:
        # A copy, because a failing send removes its subscriber mid-iteration.
        for subscriber in list(self.subscribers):
            try:
                await subscriber(message)
            except Exception:  # noqa: BLE001 - a dead subscriber must not stop the rest
                self.subscribers.discard(subscriber)

    async def on_upstream(self, event: dict) -> None:
        kind = event.get("kind")

        if kind == "quote":
            ts_ms = int(event["t"])
            bid = float(event["bid"])
            await self.broadcast(
                QuoteMessage(symbol=self.epic, time=ts_ms, bid=bid, ask=float(event["ask"]))
            )
            # The bid side, matching both the sealed candles and the REST history.
            bar = self.forming.on_quote(ts_ms, bid)
            if bar is not None:
                await self.broadcast(self.candle_message(bar, forming=True))

        elif kind == "sealed":
            bar = self.forming.on_sealed(
                Bar(
                    time=int(event["t"]) // 1000,
                    open=float(event["o"]),
                    high=float(event["h"]),
                    low=float(event["l"]),
                    close=float(event["c"]),
                )
            )
            await self.broadcast(self.candle_message(bar, forming=False))

        elif kind == "status":
            self.state = event["state"]
            await self.broadcast(StatusMessage(state=event["state"]))

        elif kind == "error":
            await self.broadcast(ErrorMessage(message=event["message"]))

    def candle_message(self, bar: Bar, forming: bool) -> CandleMessage:
        return CandleMessage(
            symbol=self.epic,
            resolution=self.resolution,
            time=bar.time,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            forming=forming,
        )


class Hub:
    def __init__(self, make_upstream: UpstreamFactory) -> None:
        self._make_upstream = make_upstream
        self._rooms: dict[tuple[str, Resolution], Room] = {}

    def room_count(self) -> int:
        return len(self._rooms)

    async def subscribe(self, epic: str, resolution: Resolution, subscriber: Subscriber) -> None:
        key = (epic, resolution)
        room = self._rooms.get(key)
        if room is None:
            room = Room(epic, resolution)
            self._rooms[key] = room
            room.upstream = self._make_upstream(epic, resolution, room.on_upstream)
            room.upstream.start()
        room.subscribers.add(subscriber)
        await subscriber(StatusMessage(state=room.state))
        if room.forming.current is not None:
            # Whatever the room has built so far, so a late joiner sees a bar rather than
            # an empty chart until the next quote.
            await subscriber(room.candle_message(room.forming.current, forming=True))

    async def unsubscribe(self, epic: str, resolution: Resolution, subscriber: Subscriber) -> None:
        key = (epic, resolution)
        room = self._rooms.get(key)
        if room is None:
            return
        room.subscribers.discard(subscriber)
        if room.subscribers:
            return
        # Nobody left: the connection is closed rather than kept warm. A stream held for
        # an absent audience still counts against the provider's session limits.
        self._rooms.pop(key, None)
        if room.upstream is not None:
            await room.upstream.stop()

    async def aclose(self) -> None:
        for room in list(self._rooms.values()):
            if room.upstream is not None:
                await room.upstream.stop()
        self._rooms.clear()
