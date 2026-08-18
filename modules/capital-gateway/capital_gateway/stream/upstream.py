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

    async def _session(self) -> None:
        cst, token = await self._tokens()
        async with websockets.connect(self._url) as ws:
            await self._subscribe(ws, cst, token)
            await self._emit({"kind": "status", "state": "connected"})
            ping = asyncio.create_task(self._ping_forever(ws, cst, token))
            try:
                async for raw in ws:
                    await self._on_message(raw)
            finally:
                ping.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await ping

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

    async def _on_message(self, raw: str | bytes) -> None:
        try:
            msg = json.loads(raw)
        except ValueError:
            return
        payload = msg.get("payload") or {}
        destination = msg.get("destination")

        if destination == "ohlc.event" and payload.get("epic") == self._epic:
            if payload.get("priceType") != _KEPT_PRICE_TYPE:
                return  # the ask-side copy of a candle already published
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
        elif destination == "quote" and payload.get("epic") == self._epic:
            await self._emit(
                {
                    "kind": "quote",
                    "t": payload["timestamp"],
                    "bid": payload["bid"],
                    "ask": payload["ofr"],
                }
            )
        elif msg.get("status") and msg.get("status") != "OK":
            # A subscription refused is silence otherwise, which reads as a quiet market.
            #
            # Only named fields are quoted, never the payload. capital.com echoes the
            # failing request back — including the `cst` and `securityToken` it carried —
            # so dumping the payload publishes the session to every subscriber.
            detail = payload.get("errorCode") or payload.get("error") or ""
            message = f"{msg['status']}: {detail}" if detail else str(msg["status"])
            await self._emit({"kind": "error", "message": message[:200]})
