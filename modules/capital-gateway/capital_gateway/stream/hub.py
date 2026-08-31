"""Rooms: who is listening to what, and the one connection each room shares. Ten tabs on one
instrument are ten subscribers and one provider session, whose per-session limit is the point."""

from __future__ import annotations

import asyncio
import contextlib
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

# Where the current period starts, as the provider reports it. Injected like the upstream, so this
# module knows no transports. ``None`` means a room publishes no forming candle rather than guessing.
CurrentPeriod = Callable[[str, Resolution], Awaitable[Bar | None]]

# How long a room waits before asking again where the current period starts. Without it a provider
# answering with the period that just ended is asked once per quote, through the same rate gate.
BOUNDARY_RETRY_SECONDS = 30.0

# Where that pacing ends up when the answer keeps being "not yet". Eight session-bound rooms asking
# every 30 seconds is 960 requests an hour on a question that does not change over a weekend.
MAX_BOUNDARY_RETRY_SECONDS = 10 * 60.0
BOUNDARY_RETRY_FACTOR = 2.0

# How often a room missing a boundary looks at whether it may ask again. This is what makes the
# boundary independent of quotes arriving — the failure of 24 August 2026, a quiet room with nothing.
BOUNDARY_TICK_SECONDS = 5.0


def next_boundary_wait(wait: float) -> float:
    """How long to wait before asking about the boundary again, after being told "not yet". Its own
    function because it is the whole of the policy, and arithmetic needs no room, provider or clock."""
    return min(wait * BOUNDARY_RETRY_FACTOR, MAX_BOUNDARY_RETRY_SECONDS)


def _no_progress(offered: Bar, held: Bar, forming: FormingCandle) -> bool:
    """Whether the provider's answer leaves the room no better off. After a seal only a later period
    helps; after a break the same period *is* the confirmation, and rejecting it silenced the room."""
    return offered.time <= held.time if forming.period_is_over else offered.time < held.time


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
        # Remembered so a subscriber joining a live room is told the feed is up, rather than
        # waiting in silence for the next provider event.
        self.state: StreamState = "connecting"
        self._current_period = current_period
        self._retry_boundary_after = 0.0
        self._retry_boundary_in = BOUNDARY_RETRY_SECONDS
        # One read at a time: a quote and the room's own timer both reach here, and overlapping
        # would spend two provider requests on one question and seed from two moments.
        self._boundary_lock = asyncio.Lock()
        self._boundary_timer: asyncio.Task | None = None

    async def place_boundary(self) -> None:
        """Ask the provider where the current period starts, at most every so often. A bar placed by
        arithmetic here is the candle this exists to stop publishing, so "not yet" waits, and longer."""
        if self._current_period is None:
            return
        async with self._boundary_lock:
            await self._place_boundary()

    async def _place_boundary(self) -> None:
        assert self._current_period is not None
        if not self.forming.needs_boundary:
            # Answered while this call waited for the lock — the other caller's answer is this
            # one's too, and asking again is the duplicate the lock exists to prevent.
            return
        now = time.monotonic()
        if now < self._retry_boundary_after:
            return

        try:
            bar = await self._current_period(self.epic, self.resolution)
        except Exception as err:  # noqa: BLE001 - a boundary read must not kill the feed
            self._wait_longer(now)
            log.warning(
                "could not read the current period for %s %s: %s",
                self.epic,
                self.resolution.value,
                err,
            )
            return

        held = self.forming.current
        if bar is None or (held is not None and _no_progress(bar, held, self.forming)):
            # Nothing to seed from. Worth a line: it is the difference between a slow provider
            # and a broken room.
            self._wait_longer(now)
            log.info(
                "%s %s: no period to build on yet; waiting",
                self.epic,
                self.resolution.value,
            )
            return
        # No pacing on success: a seeded room stops needing a boundary, so the next time one is
        # wanted is news rather than a retry, and the window starts short again for it.
        self._retry_boundary_in = BOUNDARY_RETRY_SECONDS
        self._retry_boundary_after = 0.0
        self.forming.seed(bar)

    def _wait_longer(self, now: float) -> None:
        """Push the next attempt out, and the one after that further still."""
        self._retry_boundary_after = now + self._retry_boundary_in
        self._retry_boundary_in = next_boundary_wait(self._retry_boundary_in)

    def watch_for_a_boundary(self) -> None:
        """Give the room a clock of its own, for the resolutions that need one. A quote used to be
        the only moment the missing boundary was noticed, which made it a hostage of the feed."""
        if self._current_period is None or not self.forming.boundary_comes_from_provider:
            return
        if self._boundary_timer is None:
            self._boundary_timer = asyncio.create_task(
                self._keep_a_boundary(),
                name=f"boundary {self.epic} {self.resolution.value}",
            )

    async def _keep_a_boundary(self) -> None:
        while True:
            await asyncio.sleep(BOUNDARY_TICK_SECONDS)
            if not self.forming.needs_boundary:
                continue
            try:
                await self.place_boundary()
            except asyncio.CancelledError:
                raise
            except Exception:  # a timer that dies quietly is the bug above, twice over
                log.exception(
                    "%s %s: the boundary timer raised", self.epic, self.resolution.value
                )

    async def stop_watching(self) -> None:
        timer, self._boundary_timer = self._boundary_timer, None
        if timer is None:
            return
        timer.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await timer

    async def deliver(self, subscriber: Subscriber, message: Message) -> bool:
        """Send to one subscriber, dropping it if the send fails. Every send comes here, welcomes
        included: a socket can die between accept and subscribe, and that must fail one subscriber."""
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
            # The quote is published either way; only the candle needs a boundary. A market with
            # no forming candle still has a price moving, and the two must not fail together.
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
                # The period may roll over while the feed is down, and the bar in hand is then
                # the wrong one to extend — cheaper to re-read than to stretch a day's candle.
                self.forming.invalidate()
                self._retry_boundary_after = 0.0
                self._retry_boundary_in = BOUNDARY_RETRY_SECONDS
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
            # Before the first quote rather than because of it: a daily period is sealed once a
            # day, so a room waiting for the provider to name the boundary published nothing.
            if room.forming.needs_boundary:
                await room.place_boundary()
            # And from here on the room asks on its own clock, so the boundary no longer
            # depends on quotes arriving at all.
            room.watch_for_a_boundary()
        room.subscribers.add(subscriber)
        if not await room.deliver(subscriber, StatusMessage(state=room.state)):
            return
        if room.forming.current is not None:
            # Whatever the room has built so far, labelled with what it is: handing a sealed bar
            # over as forming would have a joiner chart a closed period as still moving.
            settled = room.forming.held_is_sealed
            await room.deliver(subscriber, room.candle_message(room.forming.current, not settled))

    async def unsubscribe(self, epic: str, resolution: Resolution, subscriber: Subscriber) -> None:
        key = (epic, resolution)
        room = self._rooms.get(key)
        if room is None:
            return
        room.subscribers.discard(subscriber)
        if room.subscribers:
            return
        # Nobody left: the connection is closed rather than kept warm. A stream held for an
        # absent audience still counts against the provider's session limits.
        self._rooms.pop(key, None)
        await room.stop_watching()
        if room.upstream is not None:
            await room.upstream.stop()

    async def aclose(self) -> None:
        for room in list(self._rooms.values()):
            await room.stop_watching()
            if room.upstream is not None:
                await room.upstream.stop()
        self._rooms.clear()
