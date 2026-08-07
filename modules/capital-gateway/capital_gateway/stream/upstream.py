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
from collections.abc import Awaitable, Callable

import websockets

from ..dtos import Resolution

# The provider asks for traffic at least every 10 minutes. Four is a wide margin, and a
# margin is worth having: the cost of pinging early is one tiny frame, the cost of
# pinging late is a dropped feed.
PING_INTERVAL_SECONDS = 4 * 60
RECONNECT_DELAY_SECONDS = 3.0

# The price side to keep. The sealed-candle event arrives twice per candle, once per
# side; forwarding both makes a chart jump the spread — about 1.8 points on US100. Bid,
# because that is the side the REST history is mapped from, so the two join cleanly.
_KEPT_PRICE_TYPE = "bid"

Emit = Callable[[dict], Awaitable[None]]
Tokens = Callable[[], Awaitable[tuple[str, str]]]


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
        while not self._stopping:
            try:
                await self._session()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - any failure here means reconnect
                await self._emit({"kind": "error", "message": str(exc)[:200]})
            if self._stopping:
                return
            await self._emit({"kind": "status", "state": "reconnecting"})
            await asyncio.sleep(RECONNECT_DELAY_SECONDS)

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
            await self._emit(
                {"kind": "error", "message": f"{msg['status']}: {json.dumps(payload)[:200]}"}
            )
