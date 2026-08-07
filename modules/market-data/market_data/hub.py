"""Fan-out to subscribers, and the seam that used to live in the browser.

A consumer that wants a chart needs two things that arrive by different roads: the series
up to now, and every change after. Joining them is the awkward part, and until this module
existed it was done in the terminal — read the history, subscribe, and hope nothing closed
in between. Something always eventually does, which is where the terminal's "on resume you
must close the gap" rule came from.

It is done here instead, once, because here it can actually be made airtight. The snapshot
is read while the room is held still and the subscriber is attached before it is released,
so there is no moment at which a candle can be neither in the snapshot nor in the changes.
The same hold covers the write: without it a candle could commit to the database after the
snapshot query ran and be broadcast afterwards, arriving twice.

The room is held by an asyncio lock rather than a database one. Everything that can attach
a subscriber or publish to one runs in this process, on this loop, so the lock covers every
path — and a database lock could not cover the in-memory subscriber set anyway.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Literal

from pydantic import BaseModel

from .models import Candle, Resolution

log = logging.getLogger(__name__)

Pair = tuple[str, Resolution]
Subscriber = Callable[["Outbound"], Awaitable[None]]


class Snapshot(BaseModel):
    """The first message on every subscription, and the only one that looks backwards.

    Carries the settled series and, separately, whatever period is currently being built.
    They are separate because they mean different things: one will never change again, the
    other changes with every quote.
    """

    kind: Literal["snapshot"] = "snapshot"
    symbol: str
    resolution: Resolution
    candles: list[Candle]
    forming: Candle | None = None


class CandleChange(BaseModel):
    """One candle, closed or still forming, said explicitly.

    One message kind for both, marked rather than split, because a consumer upserts by
    period start and two message types would only make it reconcile them itself. The mark
    is what stops a chart treating a period still moving as settled.
    """

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
        # Held in memory and never stored. A forming candle changes with every quote and
        # understates its own range until the period closes; a subscriber joining midway
        # still wants it, or its chart is missing the bar the price is actually in.
        self.forming: Candle | None = None


class Hub:
    def __init__(self) -> None:
        self._rooms: dict[Pair, Room] = {}

    def room_count(self) -> int:
        return len(self._rooms)

    def subscriber_count(self, symbol: str, resolution: Resolution) -> int:
        room = self._rooms.get((symbol, resolution))
        return len(room.subscribers) if room else 0

    def _room(self, symbol: str, resolution: Resolution) -> Room:
        return self._rooms.setdefault((symbol, resolution), Room())

    @asynccontextmanager
    async def held(self, symbol: str, resolution: Resolution):
        """Hold one room still.

        Whatever happens inside is atomic with respect to subscribing: a producer wraps
        its database write and its broadcast in this, so a subscriber's snapshot either
        already contains the candle or is followed by the message carrying it — never
        both, and never neither.
        """
        async with self._room(symbol, resolution).lock:
            yield

    async def publish(
        self, symbol: str, resolution: Resolution, candle: Candle, *, store=None
    ) -> None:
        """Send a candle to everyone listening, optionally storing it first.

        `store` runs inside the hold. That is the whole point: a write that commits
        outside it can land between a subscriber's snapshot query and its attachment, and
        the same period then arrives twice.
        """
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
        """Attach a subscriber, having first sent it the snapshot it needs.

        The read and the attachment happen under the same hold, which is what makes the
        seam airtight — and is the reason a consumer no longer has to close a gap after
        reconnecting.
        """
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
