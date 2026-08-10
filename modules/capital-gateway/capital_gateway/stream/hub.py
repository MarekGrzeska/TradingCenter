"""Rooms: who is listening to what, and the one connection each room shares.

The sharing is the point. Ten browser tabs on the same instrument are ten subscribers
and one connection to capital.com — the provider limits how many a session may hold, and
opening one per subscriber spends that limit on duplicate data.

This is also where a provider event becomes a published message: the upstream emits
sealed candles and quotes, the room folds them through its forming candle, and what
leaves is the contract in ``messages``.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable

from ..dtos import Resolution
from .forming import Bar, FormingCandle
from .messages import (
    CandleMessage,
    ErrorMessage,
    Message,
    QuoteMessage,
    StatusMessage,
    StreamState,
)
from .upstream import Upstream

log = logging.getLogger(__name__)

Subscriber = Callable[[Message], Awaitable[None]]
UpstreamFactory = Callable[[str, Resolution, Callable[[dict], Awaitable[None]]], Upstream]

# Where the current period starts, as the provider reports it. Injected the same way the
# upstream is, so this module still knows nothing about transports. ``None`` means the
# provider could not say — a room then publishes no forming candle rather than guessing
# one, which for a daily boundary is the whole point.
CurrentPeriod = Callable[[str, Resolution], Awaitable[Bar | None]]

# How long a room waits before asking again where the current period starts. Without it a
# provider that keeps answering with the period that just ended would be asked once per
# quote — hundreds of times a minute on a liquid instrument, through the same rate gate
# an operator's chart reads through. Every quote still moves the price; only the boundary
# lookup is paced.
BOUNDARY_RETRY_SECONDS = 30.0


class Room:
    def __init__(
        self,
        epic: str,
        resolution: Resolution,
        current_period: CurrentPeriod | None = None,
    ) -> None:
        self.epic = epic
        self.resolution = resolution
        self.subscribers: set[Subscriber] = set()
        self.forming = FormingCandle(resolution)
        self.upstream: Upstream | None = None
        # Remembered so a subscriber joining a live room is told the feed is up rather
        # than waiting in silence for the next provider event.
        self.state: StreamState = "connecting"
        self._current_period = current_period
        self._retry_boundary_after = 0.0

    async def place_boundary(self) -> None:
        """Ask the provider where the current period starts, at most every so often.

        Only ever reached for a resolution whose boundary follows the venue's session.
        A provider that answers with the period that has already ended — which happens
        between a period closing and the next one producing its first candle — leaves the
        room silent and tries again later, because a bar placed by arithmetic here is the
        candle this whole change exists to stop publishing.
        """
        if self._current_period is None:
            return
        now = time.monotonic()
        if now < self._retry_boundary_after:
            return

        try:
            bar = await self._current_period(self.epic, self.resolution)
        except Exception as err:  # noqa: BLE001 - a boundary read must not kill the feed
            self._retry_boundary_after = now + BOUNDARY_RETRY_SECONDS
            log.warning(
                "could not read the current period for %s %s: %s",
                self.epic,
                self.resolution.value,
                err,
            )
            return

        held = self.forming.current
        if bar is None or (held is not None and bar.time <= held.time):
            # Nothing newer than the period already known to be over. Saying so is worth
            # a line: it is the difference between "the provider is slow to open the next
            # candle" and "this room is broken".
            self._retry_boundary_after = now + BOUNDARY_RETRY_SECONDS
            log.info(
                "%s %s: no period newer than the one that closed; waiting",
                self.epic,
                self.resolution.value,
            )
            return
        # No pacing on success: a seeded room stops needing a boundary, so nothing calls
        # this again until the provider seals the period or the feed drops — and both are
        # news rather than a retry.
        self.forming.seed(bar)

    async def deliver(self, subscriber: Subscriber, message: Message) -> bool:
        """Send to one subscriber, dropping it if the send fails.

        Every send goes through here, including the welcome messages: a socket can die
        between the connection being accepted and the subscription completing, and an
        exception escaping there fails the subscribe call rather than that subscriber.
        """
        try:
            await subscriber(message)
        except Exception:  # noqa: BLE001 - a dead subscriber must not stop the rest
            self.subscribers.discard(subscriber)
            return False
        return True

    async def broadcast(self, message: Message) -> None:
        # A copy, because a failing send removes its subscriber mid-iteration.
        for subscriber in list(self.subscribers):
            await self.deliver(subscriber, message)

    async def on_upstream(self, event: dict) -> None:
        kind = event.get("kind")

        if kind == "quote":
            ts_ms = int(event["t"])
            bid = float(event["bid"])
            await self.broadcast(
                QuoteMessage(symbol=self.epic, time=ts_ms, bid=bid, ask=float(event["ask"]))
            )
            # The quote is published either way; only the candle needs a boundary. A
            # market with no forming candle is still a market whose price is moving, and
            # the two must not fail together.
            if self.forming.needs_boundary:
                await self.place_boundary()
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
            if self.state != "connected":
                # The period may roll over while the feed is down, and the bar in hand is
                # then the wrong one to extend. Cheaper to re-read the boundary than to
                # publish a day's candle stretched across two days.
                self.forming.invalidate()
                self._retry_boundary_after = 0.0
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
    def __init__(
        self, make_upstream: UpstreamFactory, current_period: CurrentPeriod | None = None
    ) -> None:
        self._make_upstream = make_upstream
        self._current_period = current_period
        self._rooms: dict[tuple[str, Resolution], Room] = {}

    def room_count(self) -> int:
        return len(self._rooms)

    async def subscribe(self, epic: str, resolution: Resolution, subscriber: Subscriber) -> None:
        key = (epic, resolution)
        room = self._rooms.get(key)
        if room is None:
            room = Room(epic, resolution, self._current_period)
            self._rooms[key] = room
            room.upstream = self._make_upstream(epic, resolution, room.on_upstream)
            room.upstream.start()
            # Before the first quote rather than because of it. A daily period is sealed
            # once a day, so a room that waited for the provider to name the boundary
            # published nothing for up to that long — the failure this answers.
            if room.forming.needs_boundary:
                await room.place_boundary()
        room.subscribers.add(subscriber)
        if not await room.deliver(subscriber, StatusMessage(state=room.state)):
            return
        if room.forming.current is not None:
            # Whatever the room has built so far, so a late joiner sees a bar rather than
            # an empty chart until the next quote.
            await room.deliver(subscriber, room.candle_message(room.forming.current, True))

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
