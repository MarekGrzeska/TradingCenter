"""The subscription: a snapshot, then every change."""

from __future__ import annotations

from fastapi import (
    APIRouter,
    Depends,
    WebSocket,
    WebSocketDisconnect,
)

from ..hub import Hub
from ..models import Candle, Resolution
from ..store import read_recent
from ..tracking import (
    is_tracked,
)
from .deps import hub

# How many settled candles a new subscriber is handed before the changes start. Enough for
# a chart to draw something immediately; a consumer wanting more asks the range endpoint,
# which is what it is for.
SNAPSHOT_CANDLES = 500

router = APIRouter()


@router.websocket("/ws/candles")
async def candle_feed(websocket: WebSocket, the_hub: Hub = Depends(hub)) -> None:
    """A snapshot, then every change.

    The subscription is the query string, so there is no client protocol to get wrong.
    """
    symbol = (websocket.query_params.get("symbol") or "").strip().upper()
    raw_resolution = websocket.query_params.get("resolution") or Resolution.MINUTE.value

    if not symbol:
        await websocket.close(code=1008, reason="symbol is required")
        return
    try:
        resolution = Resolution(raw_resolution)
    except ValueError:
        await websocket.close(code=1008, reason=f"unknown resolution {raw_resolution!r}")
        return

    db = websocket.app.state.pool
    async with db.acquire() as conn:
        if not await is_tracked(conn, symbol, resolution):
            # Refused before the handshake. Accepting and then closing would look like a
            # feed that died rather than a pair nobody chose to collect — and subscribing
            # must not quietly start collecting it, because that is the decision the
            # ceiling exists to keep deliberate.
            await websocket.close(
                code=1008, reason=f"{symbol} {resolution.value} is not being collected"
            )
            return

    await websocket.accept()

    async def send(message) -> None:
        await websocket.send_json(message.model_dump(mode="json"))

    async def read_settled() -> list[Candle]:
        async with db.acquire() as conn:
            return list(await read_recent(conn, symbol, resolution, SNAPSHOT_CANDLES))

    await the_hub.subscribe(symbol, resolution, send, read_settled)
    try:
        # Nothing to read, but receiving is how a disconnect is noticed; without it the
        # handler returns and the socket closes.
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await the_hub.unsubscribe(symbol, resolution, send)
