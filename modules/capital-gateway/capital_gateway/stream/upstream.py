"""The outbound connection to capital.com's streaming endpoint. Not a reverse proxy: the protocol
wants the session tokens inside every message, so something must own the connection and hide them."""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from collections.abc import Awaitable, Callable

import websockets

from ..dtos import Resolution

# The provider asks for traffic at least every 10 minutes. Pinging early costs one tiny frame,
# pinging late costs the feed.
PING_INTERVAL_SECONDS = 4 * 60
RECONNECT_DELAY_SECONDS = 3.0

# What the delay climbs to while reconnecting keeps failing. Three seconds flat is right for a
# dropped socket and wrong for a session that will not renew: 20 requests a minute, forever.
MAX_RECONNECT_DELAY_SECONDS = 60.0
RECONNECT_BACKOFF_FACTOR = 2.0

# How long a connection may deliver no market data before it is treated as broken. Measured 24 Aug
# 2026: one room silent for fourteen hours on a healthy socket — only counting data can see that.
SILENCE_TOLERANCE_SECONDS = 120.0

# Where the tolerance ends up when reconnecting keeps producing silence — which is what a closed
# market looks like, and a market can be closed all weekend.
MAX_SILENCE_TOLERANCE_SECONDS = 10 * 60.0
SILENCE_TOLERANCE_FACTOR = 2.0

# How long a session must have lasted for the next drop to start from the short delay again.
# Measured on the socket, not on how it ended: dead tokens close cleanly after an error frame.
HEALTHY_SESSION_SECONDS = 30.0

# The price side to keep. The sealed-candle event arrives once per side, and forwarding both makes
# a chart jump the spread — about 1.8 points on US100. Bid, because REST history is mapped from it.
_KEPT_PRICE_TYPE = "bid"

Emit = Callable[[dict], Awaitable[None]]
Tokens = Callable[[], Awaitable[tuple[str, str]]]
# Waits for a slot in the provider's request budget. A subscribe frame counts against the same
# 10 req/s as a REST call: twenty rooms reconnecting together answered `error.too-many.requests`.
Pace = Callable[[], Awaitable[None]]


class SilentFeed(Exception):
    """The provider stopped sending market data without closing the connection. An exception because
    that is what the loop already understands: `_session` raising is how a session ends."""


def next_silence_tolerance(tolerance: float, heard_data: bool) -> float:
    """How long the next session may say nothing before it is written off. A run of silent sessions
    is a shut market or a pair the provider will not serve, and neither answers to asking sooner."""
    if heard_data:
        return SILENCE_TOLERANCE_SECONDS
    return min(tolerance * SILENCE_TOLERANCE_FACTOR, MAX_SILENCE_TOLERANCE_SECONDS)


def next_reconnect_delay(delay: float, session_lasted: float) -> float:
    """How long to wait before the attempt after this one. A session that stood up for a while is
    evidence the far side is fine, so the next drop is treated as the first one again."""
    if session_lasted >= HEALTHY_SESSION_SECONDS:
        return RECONNECT_DELAY_SECONDS
    return min(delay * RECONNECT_BACKOFF_FACTOR, MAX_RECONNECT_DELAY_SECONDS)


class Upstream:
    """One connection for one ``(epic, resolution)``, feeding a callback. Knows nothing about
    subscribers: it emits provider events already stripped of the provider's shape."""

    def __init__(
        self,
        stream_url: str,
        epic: str,
        resolution: Resolution,
        tokens: Tokens,
        emit: Emit,
        pace: Pace | None = None,
    ) -> None:
        self._url = stream_url
        self._epic = epic
        self._resolution = resolution
        self._tokens = tokens
        self._emit = emit
        self._pace = pace
        self._task: asyncio.Task | None = None
        self._stopping = False
        self._silence_tolerance = SILENCE_TOLERANCE_SECONDS
        self._heard_data = False

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stopping = True
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _run(self) -> None:
        """Connect, subscribe, read, and do it again after a drop. The loop is the reconnection
        policy: a subscriber should see a gap in prices, not a dead socket it has to notice."""
        delay = RECONNECT_DELAY_SECONDS
        while not self._stopping:
            started = time.monotonic()
            self._heard_data = False
            try:
                await self._session()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - any failure here means reconnect
                await self._emit({"kind": "error", "message": str(exc)[:200]})
            if self._stopping:
                return
            lasted = time.monotonic() - started
            await self._emit({"kind": "status", "state": "reconnecting"})
            await asyncio.sleep(delay)
            # Computed after the sleep, so the first reconnect after a drop is as quick as it
            # has always been and only a *run* of failures is slowed down.
            delay = next_reconnect_delay(delay, lasted)
            # The silence tolerance grows on its own schedule: what widens it is a session that
            # carried nothing, which is not a session that ended quickly.
            self._silence_tolerance = next_silence_tolerance(
                self._silence_tolerance, self._heard_data
            )

    async def _session(self) -> None:
        cst, token = await self._tokens()
        async with websockets.connect(self._url) as ws:
            await self._subscribe(ws, cst, token)
            await self._emit({"kind": "status", "state": "connected"})
            ping = asyncio.create_task(self._ping_forever(ws, cst, token))
            try:
                await self._read_until_silent(ws)
            finally:
                ping.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await ping

    async def _read_until_silent(self, ws) -> None:
        """Read frames until the socket ends — or until the data stops arriving. A deadline rather
        than a per-read timeout: keepalive answers would restart the timeout without proving anything."""
        loop = asyncio.get_running_loop()
        frames = ws.__aiter__()
        deadline = loop.time() + self._silence_tolerance
        while True:
            try:
                raw = await asyncio.wait_for(frames.__anext__(), deadline - loop.time())
            except StopAsyncIteration:
                return
            except TimeoutError:
                raise SilentFeed(
                    f"no market data for {self._epic} {self._resolution.value} in "
                    f"{self._silence_tolerance:.0f}s, though the connection is open"
                ) from None
            if await self._on_message(raw):
                self._heard_data = True
                deadline = loop.time() + self._silence_tolerance

    async def _subscribe(self, ws, cst: str, token: str) -> None:
        await self._take_a_slot()
        await ws.send(
            json.dumps(
                {
                    "destination": "OHLCMarketData.subscribe",
                    "correlationId": "ohlc",
                    "cst": cst,
                    "securityToken": token,
                    "payload": {
                        "epics": [self._epic],
                        "resolutions": [self._resolution.value],
                        "type": "classic",
                    },
                }
            )
        )
        await self._take_a_slot()
        await ws.send(
            json.dumps(
                {
                    "destination": "marketData.subscribe",
                    "correlationId": "quote",
                    "cst": cst,
                    "securityToken": token,
                    "payload": {"epics": [self._epic]},
                }
            )
        )

    async def _take_a_slot(self) -> None:
        if self._pace is not None:
            await self._pace()

    async def _ping_forever(self, ws, cst: str, token: str) -> None:
        while True:
            await asyncio.sleep(PING_INTERVAL_SECONDS)
            await ws.send(
                json.dumps(
                    {
                        "destination": "ping",
                        "correlationId": "ping",
                        "cst": cst,
                        "securityToken": token,
                    }
                )
            )

    async def _on_message(self, raw: str | bytes) -> bool:
        """Translate one frame, and say whether it carried market data. The return value is what the
        silence watchdog counts: a keepalive and a refusal both arrive as frames and prove nothing."""
        try:
            msg = json.loads(raw)
        except ValueError:
            return False
        payload = msg.get("payload") or {}
        destination = msg.get("destination")

        if destination == "ohlc.event" and payload.get("epic") == self._epic:
            if payload.get("priceType") != _KEPT_PRICE_TYPE:
                return True  # the ask-side copy of a candle already published
            await self._emit(
                {
                    "kind": "sealed",
                    "t": payload["t"],
                    "o": payload["o"],
                    "h": payload["h"],
                    "l": payload["l"],
                    "c": payload["c"],
                }
            )
            return True
        elif destination == "quote" and payload.get("epic") == self._epic:
            await self._emit(
                {
                    "kind": "quote",
                    "t": payload["timestamp"],
                    "bid": payload["bid"],
                    "ask": payload["ofr"],
                }
            )
            return True
        elif msg.get("status") and msg.get("status") != "OK":
            # A subscription refused is silence otherwise, which reads as a quiet market. Only named
            # fields are quoted: capital.com echoes the request back, session tokens included.
            detail = payload.get("errorCode") or payload.get("error") or ""
            message = f"{msg['status']}: {detail}" if detail else str(msg["status"])
            await self._emit({"kind": "error", "message": message[:200]})
        return False
