"""Fan-out to subscribers, and the seam that used to live in the browser. The snapshot is read while
the room is held still and the subscriber attached before it is released, so nothing falls between."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Literal

from pydantic import BaseModel

from .models import Candle, Resolution
from .periods import period_length

log = logging.getLogger(__name__)

Pair = tuple[str, Resolution]
Subscriber = Callable[["Outbound"], Awaitable[None]]


class Snapshot(BaseModel):
    """The first message on every subscription, and the only one that looks backwards. The settled
    series and the period being built are separate because one will never change again."""

    kind: Literal["snapshot"] = "snapshot"
    symbol: str
    resolution: Resolution
    candles: list[Candle]
    forming: Candle | None = None


class CandleChange(BaseModel):
    """One candle, closed or still forming, said explicitly. One message kind for both, marked rather
    than split, because a consumer upserts by period start."""

    kind: Literal["candle"] = "candle"
    symbol: str
    resolution: Resolution
    candle: Candle


Outbound = Snapshot | CandleChange


class Room:
    """One pair's subscribers, and the last forming candle seen for it."""

    def __init__(self) -> None:
        self.subscribers: set[Subscriber] = set()
        self.lock = asyncio.Lock()
        # Held in memory and never stored: a forming candle understates its own range until the
        # period closes, and a subscriber joining midway still wants it.
        self.forming: Candle | None = None


class Hub:
    def __init__(self) -> None:
        self._rooms: dict[Pair, Room] = {}

    def room_count(self) -> int:
        return len(self._rooms)

    def subscriber_count(self, symbol: str, resolution: Resolution) -> int:
        room = self._rooms.get((symbol, resolution))
        return len(room.subscribers) if room else 0

    def forming(self, symbol: str, resolution: Resolution) -> Candle | None:
        """The candle currently being built for one pair, or None. `.get`, never `_room`: a read that
        created a room would leave one behind forever. No lock — `publish` assigns between two awaits."""
        room = self._rooms.get((symbol, resolution))
        return room.forming if room else None

    def forming_resolutions(self, symbol: str) -> list[Resolution]:
        """Which resolutions this symbol has a forming candle for, finest first. What is arriving now
        rather than what the operator asked to track — a stalled minute feed still has a price on HOUR."""
        live = [
            resolution
            for (candidate, resolution), room in self._rooms.items()
            if candidate == symbol and room.forming is not None
        ]
        return sorted(live, key=period_length)

    def _room(self, symbol: str, resolution: Resolution) -> Room:
        return self._rooms.setdefault((symbol, resolution), Room())

    @asynccontextmanager
    async def held(self, symbol: str, resolution: Resolution):
        """Hold one room still. Whatever happens inside is atomic with respect to subscribing, so a
        subscriber's snapshot either contains the candle or is followed by the message carrying it."""
        async with self._room(symbol, resolution).lock:
            yield

    async def publish(
        self, symbol: str, resolution: Resolution, candle: Candle, *, store=None
    ) -> None:
        """Send a candle to everyone listening, optionally storing it first. `store` runs inside the
        hold: a write committing outside it can land between a snapshot query and its attachment."""
        room = self._room(symbol, resolution)
        async with room.lock:
            if store is not None:
                await store()
            room.forming = candle if candle.forming else None
            await self._send_to_all(room, CandleChange(symbol=symbol, resolution=resolution, candle=candle))

    async def subscribe(
        self,
        symbol: str,
        resolution: Resolution,
        subscriber: Subscriber,
        read_settled: Callable[[], Awaitable[list[Candle]]],
    ) -> None:
        """Attach a subscriber, having first sent it the snapshot it needs. The read and the attachment
        happen under one hold, which is why a consumer no longer closes a gap after reconnecting."""
        room = self._room(symbol, resolution)
        async with room.lock:
            settled = await read_settled()
            snapshot = Snapshot(
                symbol=symbol, resolution=resolution, candles=list(settled), forming=room.forming
            )
            # Sent before the subscriber joins the set, so a failure here is this
            # subscriber's problem rather than a half-attached room.
            await subscriber(snapshot)
            room.subscribers.add(subscriber)

    async def unsubscribe(
        self, symbol: str, resolution: Resolution, subscriber: Subscriber
    ) -> None:
        room = self._rooms.get((symbol, resolution))
        if room is None:
            return
        async with room.lock:
            room.subscribers.discard(subscriber)
            if not room.subscribers and room.forming is None:
                self._rooms.pop((symbol, resolution), None)

    async def _send_to_all(self, room: Room, message: Outbound) -> None:
        # A copy, because a failing send drops its subscriber mid-iteration.
        for subscriber in list(room.subscribers):
            try:
                await subscriber(message)
            except Exception:  # noqa: BLE001 - one dead socket must not stop the rest
                log.info("dropping a subscriber whose send failed")
                room.subscribers.discard(subscriber)
