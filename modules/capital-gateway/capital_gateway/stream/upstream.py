"""The outbound connection to capital.com's streaming endpoint.

Why this cannot be a reverse proxy: the streaming protocol wants ``cst`` and
``securityToken`` **inside every message**, not as connection headers. Nothing that only
forwards bytes can supply them, so something has to own the connection — and once it
does, the tokens never reach a subscriber.

Two subscriptions, because neither is sufficient alone. Measured on US100 over 60 s:

    OHLCMarketData.subscribe -> ohlc.event   0 times   full o/h/l/c, only on close
    marketData.subscribe     -> quote      296 times   bid/ask only, no candle

The candle event seals a bar; the quotes are what make the price move between seals.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from collections.abc import Awaitable, Callable

import websockets

from ..dtos import Resolution

# The provider asks for traffic at least every 10 minutes. Four is a wide margin, and a
# margin is worth having: the cost of pinging early is one tiny frame, the cost of
# pinging late is a dropped feed.
PING_INTERVAL_SECONDS = 4 * 60
RECONNECT_DELAY_SECONDS = 3.0

# What the delay climbs to while reconnecting keeps failing, and how fast it climbs.
#
# Three seconds flat is right for the failure this loop was written for — a socket
# dropped over hours — and wrong for the other one: a session the provider will not renew
# at all. There the loop cannot succeed, and at a fixed three seconds it asks anyway, 20
# times a minute, forever. capital.com counts its 10 requests/second against the
# *account*, so a room in that state spends the whole gateway's allowance on a question
# already answered. Sixty seconds is the ceiling because a feed that is going to come
# back has usually come back by then, and a minute of silence is a gap a subscriber can
# read on the chart.
MAX_RECONNECT_DELAY_SECONDS = 60.0
RECONNECT_BACKOFF_FACTOR = 2.0

# How long a connection may deliver no market data before it is treated as broken.
#
# The failure this answers, measured on 24 August 2026: one room received nothing for
# fourteen hours while 28 others on the same session carried 47 to 265 quotes per 25
# seconds. The socket was open the whole time — `websockets` pings every 20 seconds and
# drops a peer that stops answering, so the transport was healthy and the *subscription*
# was dead. Nothing that watches the socket can see that; only counting data can.
#
# Data, and not any frame: the provider answers a keepalive, and a connection whose
# subscriptions are gone still answers it. A watchdog fed by those would have sat through
# all fourteen hours. Two minutes is two orders of magnitude past what a live feed does.
SILENCE_TOLERANCE_SECONDS = 120.0

# Where the tolerance ends up when reconnecting keeps producing silence — which is what a
# closed market looks like, and a market can be closed all weekend. At the ceiling, the 29
# rooms this account runs cost about 0.05 requests a second; at a flat two minutes they
# would cost ten times that for two days, out of ten per second shared with every read an
# operator makes.
MAX_SILENCE_TOLERANCE_SECONDS = 10 * 60.0
SILENCE_TOLERANCE_FACTOR = 2.0

# How long a session has to have lasted for the next drop to start from the short delay
# again. Measured on the socket rather than on how it ended, because the failure that
# needs backing off does not always raise: dead tokens are answered with an error frame
# and a close, which reads as a clean end to a session that lasted a moment.
HEALTHY_SESSION_SECONDS = 30.0

# The price side to keep. The sealed-candle event arrives twice per candle, once per
# side; forwarding both makes a chart jump the spread — about 1.8 points on US100. Bid,
# because that is the side the REST history is mapped from, so the two join cleanly.
_KEPT_PRICE_TYPE = "bid"

Emit = Callable[[dict], Awaitable[None]]
Tokens = Callable[[], Awaitable[tuple[str, str]]]


class SilentFeed(Exception):
    """The provider stopped sending market data without closing the connection.

    An exception because that is what the loop already understands: `_session` raising is
    how a session ends, and ending it is exactly the answer here.
    """


def next_silence_tolerance(tolerance: float, heard_data: bool) -> float:
    """How long the next session may say nothing before it is written off.

    A session that carried data was a healthy one, so the next one starts from the short
    tolerance again. A run of sessions that carried none is either a market that is shut
    or a provider that will not serve this pair right now, and neither is answered by
    asking every two minutes for two days.
    """
    if heard_data:
        return SILENCE_TOLERANCE_SECONDS
    return min(tolerance * SILENCE_TOLERANCE_FACTOR, MAX_SILENCE_TOLERANCE_SECONDS)


def next_reconnect_delay(delay: float, session_lasted: float) -> float:
    """How long to wait before the attempt after this one.

    A separate function because it is the whole of the policy, and a policy that lives
    only inside a `while` needs a socket, a clock and a scheduler to ask a question about
    arithmetic.

    A session that stood up for a while is evidence the far side is fine, so the next
    drop is treated as the first one again — without that, a feed reconnecting once an
    hour would end the day waiting a minute for every gap.
    """
    if session_lasted >= HEALTHY_SESSION_SECONDS:
        return RECONNECT_DELAY_SECONDS
    return min(delay * RECONNECT_BACKOFF_FACTOR, MAX_RECONNECT_DELAY_SECONDS)


class Upstream:
    """One connection for one ``(epic, resolution)``, feeding a callback.

    Knows nothing about subscribers: it emits provider events already stripped of the
    provider's shape, and the hub decides who hears them.
    """

    def __init__(
        self,
        stream_url: str,
        epic: str,
        resolution: Resolution,
        tokens: Tokens,
        emit: Emit,
    ) -> None:
        self._url = stream_url
        self._epic = epic
        self._resolution = resolution
        self._tokens = tokens
        self._emit = emit
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
        """Connect, subscribe, read, and do it again after a drop.

        The loop is the reconnection policy: a dropped feed is normal over hours, and a
        subscriber should see a gap in prices, not a dead socket it has to notice.
        """
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
            # Computed after the sleep, so the first reconnect after a drop is as quick as
            # it has always been and only a *run* of failures is slowed down.
            delay = next_reconnect_delay(delay, lasted)
            # The silence tolerance grows on its own schedule: what widens it is a session
            # that carried nothing, which is not the same thing as one that ended quickly.
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
        """Read frames until the socket ends — or until the data stops arriving.

        A deadline rather than a timeout on each read, because the two are not the same
        question once keepalive answers are on the wire: every frame would restart a
        per-read timeout, and the frames that prove a *subscription* is alive are only the
        ones carrying market data. So the deadline moves for those and for nothing else.
        """
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
        """Translate one frame, and say whether it carried market data.

        The return value is what the silence watchdog counts. A keepalive answer and a
        refusal both arrive as frames and neither proves the subscription is still being
        served — which is the whole distinction the watchdog rests on.
        """
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
            # A subscription refused is silence otherwise, which reads as a quiet market.
            #
            # Only named fields are quoted, never the payload. capital.com echoes the
            # failing request back — including the `cst` and `securityToken` it carried —
            # so dumping the payload publishes the session to every subscriber.
            detail = payload.get("errorCode") or payload.get("error") or ""
            message = f"{msg['status']}: {detail}" if detail else str(msg["status"])
            await self._emit({"kind": "error", "message": message[:200]})
        return False
