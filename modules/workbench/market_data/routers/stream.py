"""The subscription: a snapshot, then every change — and the ticket that opens it."""

from __future__ import annotations

import logging

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)

from ..contract import Problem, StreamTicketOut
from ..hub import Hub
from ..models import Candle, Resolution
from ..store import read_recent
from ..tickets import TicketStore
from ..tracking import (
    is_tracked,
)
from .deps import hub

log = logging.getLogger(__name__)

# How many settled candles a new subscriber is handed before the changes start. Enough for a chart to
# draw immediately; a consumer wanting more asks the range endpoint.
SNAPSHOT_CANDLES = 500

# What a platform authenticator puts on every request it lets through. The id is the
# stable half — a name can be changed, an object id cannot.
PRINCIPAL_ID_HEADER = "X-MS-CLIENT-PRINCIPAL-ID"
PRINCIPAL_NAME_HEADER = "X-MS-CLIENT-PRINCIPAL-NAME"

# Recorded on a ticket issued with nobody standing in front of the module. Only reachable
# while `require_authenticated_principal` is off, which means local development.
UNAUTHENTICATED = "anonymous"

router = APIRouter()


# The path deliberately does not begin with `/ws`: that prefix is where the one Easy Auth exemption
# lives, and a ticket factory beside it is one careless prefix match from being exempt too.
@router.post(
    "/stream-tickets",
    tags=["stream"],
    response_model=StreamTicketOut,
    responses={401: {"model": Problem}},
    summary="A one-time ticket for opening the candle stream",
    description=(
        "A browser cannot put a header on a WebSocket handshake, so a consumer running in "
        "one proves who it is here — where headers work — and spends the answer there. "
        "The ticket is good for one handshake and for a few seconds; asking again is the "
        "only way to get another, including after a dropped connection."
    ),
)
async def issue_stream_ticket(request: Request) -> StreamTicketOut:
    settings = request.app.state.settings
    identity = (
        request.headers.get(PRINCIPAL_ID_HEADER) or request.headers.get(PRINCIPAL_NAME_HEADER) or ""
    ).strip()

    if not identity:
        if settings.require_authenticated_principal:
            log.warning("stream ticket refused: the request carries no authenticated principal")
            raise HTTPException(status_code=401, detail="not authenticated")
        identity = UNAUTHENTICATED

    tickets: TicketStore = request.app.state.tickets
    ticket = tickets.issue(identity)
    # The fact and who for, never the value — this line is the one a leak would come out
    # of, and it is written on every subscription the terminal opens.
    log.info("stream ticket issued to %s", identity)
    return StreamTicketOut(
        ticket=ticket.value,
        expires_in_seconds=int(tickets.ttl.total_seconds()),
    )


@router.websocket("/ws/candles")
async def candle_feed(websocket: WebSocket, the_hub: Hub = Depends(hub)) -> None:
    """A snapshot, then every change.

    The subscription is the query string, so there is no client protocol to get wrong.
    """
    # First, and before the database is touched. This path is outside Easy Auth, so the ticket is all
    # that stands between the internet and the stream.
    ticket = websocket.app.state.tickets.spend(websocket.query_params.get("ticket"))
    if ticket is None:
        # One message for all four cases — missing, unknown, expired, already spent. Which one it
        # was is not the caller's business, and saying turns the refusal into an oracle.
        log.warning("stream handshake refused: no valid ticket")
        await websocket.close(code=1008, reason="a valid stream ticket is required")
        return

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
            # Refused before the handshake: accepting and closing would look like a feed that died.
            # And subscribing must not quietly start collecting a pair nobody chose.
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
