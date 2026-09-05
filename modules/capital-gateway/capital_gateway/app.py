"""The published surface: FastAPI over the adapter, plus the streaming WebSocket. The credential
check is middleware, not a dependency: the one route someone forgets is the one that ships open."""

from __future__ import annotations

import hmac
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from . import telemetry

# Must run before `from fastapi import FastAPI` below, not merely before `FastAPI(...)` is called:
# the auto-instrumentation patches the class attribute, and the import binds this module's name.
telemetry.configure()

log = logging.getLogger(__name__)

from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

from .adapter import CapitalAdapter
from .caller_access import (
    PRINCIPAL_HEADER,
    browser_caller_may_reach,
    calling_application,
)
from .client import CapitalClient
from .config import API_KEY_HEADER, Settings, is_production
from .dtos import (
    Account,
    AssetClass,
    Candle,
    CandleHistory,
    Capabilities,
    Instrument,
    InstrumentPage,
    InstrumentTerms,
    Order,
    PlaceOrderRequest,
    Position,
    Resolution,
    UpdatePositionRequest,
    WorkingOrder,
)
from .errors import GatewayError
from .history import parse_candle_ts
from .stream.forming import Bar
from .stream.hub import Hub
from .stream.upstream import Upstream


async def stream_tokens_for(client: CapitalClient) -> tuple[str, str]:
    """The pair the streaming protocol needs, from a session known to still answer. A stream makes
    no REST calls, so its tokens expire unwatched; checked here, and raised on, or it reconnects forever."""
    resp = await client.session_details()
    if not resp.is_success:
        raise GatewayError(
            "capital.com would not confirm the session the stream borrows "
            f"(HTTP {resp.status_code}); refusing to subscribe with tokens it has "
            "not just accepted",
            status_code=502,
        )
    return client.stream_tokens()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Settings first, and outside a try: a live URL or a missing credential must stop
    # the process here rather than surface later as a failing request.
    settings = Settings()  # type: ignore[call-arg]
    client = CapitalClient(settings)

    async def tokens() -> tuple[str, str]:
        return await stream_tokens_for(client)

    adapter = CapitalAdapter(client)

    async def current_period(epic: str, resolution: Resolution) -> Bar | None:
        """Where the period a room is currently building starts. Only DAY and WEEK, whose boundary
        follows the venue rather than the clock — the provider's newest candle is that boundary."""
        candles = await adapter.get_candles(epic, resolution, 1)
        if not candles:
            return None
        newest = candles[-1]
        if not newest.forming or newest.open is None:
            # A settled candle says where a period that has *ended* began, which is not
            # the question. Left unanswered rather than approximated.
            return None
        return Bar(
            time=int(parse_candle_ts(newest.ts).timestamp()),
            open=newest.open,
            high=newest.high if newest.high is not None else newest.open,
            low=newest.low if newest.low is not None else newest.open,
            close=newest.close if newest.close is not None else newest.open,
        )

    hub = Hub(
        lambda epic, resolution, emit: Upstream(
            settings.capital_stream_url, epic, resolution, tokens, emit, pace=client.pace
        ),
        current_period,
    )

    app.state.settings = settings
    app.state.client = client
    app.state.adapter = adapter
    app.state.hub = hub
    try:
        yield
    finally:
        await hub.aclose()
        await client.aclose()


# The routes reachable with no credential: the platform's restart probe, and the schema pages a
# browser fetches without the key. Exact matches, not prefixes — a prefix is a typo from a real route.
_UNAUTHENTICATED_PATHS = frozenset({"/", "/docs", "/openapi.json"})


class GatewayDoor(BaseHTTPMiddleware):
    """Who gets past the door, and how far. The application a platform-validated token names decides —
    a module reaches everything, a browser the account (`caller_access.py`) — and the shared key opens an
    HTTP route only off production, where no platform stands in front to name anyone. On production it
    is the credential of `/ws/stream` alone, checked inside that handler."""

    async def dispatch(self, request: Request, call_next):
        if request.url.path in _UNAUTHENTICATED_PATHS:
            return await call_next(request)

        settings = request.app.state.settings
        provided = request.headers.get(API_KEY_HEADER, "")
        application = calling_application(request.headers.get(PRINCIPAL_HEADER))

        if application and application in settings.module_caller_application_ids:
            return await call_next(request)
        if application and application in settings.browser_caller_application_ids:
            if not browser_caller_may_reach(request.url.path):
                # A refusal about permission, not about the provider: this request never left
                # the module, and naming capital.com would send the reader to the wrong place.
                return JSONResponse(
                    status_code=403,
                    content={"detail": "this caller may reach the account, not this path"},
                )
            return await call_next(request)

        # Compared as bytes: hmac.compare_digest raises TypeError on a `str` holding a non-ASCII
        # character, so encoding first turns a garbage header into the intended 401, not a 500.
        expected: str = settings.gateway_api_key
        if (
            not is_production()
            and provided
            and hmac.compare_digest(provided.encode(), expected.encode())
        ):
            return await call_next(request)

        # The refusal says which door it was: until 21 August 2026 it answered 401 silently, and
        # three different faults produced that same silence. An application id is public; the key is not.
        log.warning(
            "refused %s: caller key %s (opens %s), principal header %s, application %s",
            request.url.path,
            "present" if provided else "absent",
            "no HTTP route in production" if is_production() else "every route locally",
            "present" if request.headers.get(PRINCIPAL_HEADER) else "absent",
            application or "unreadable",
        )
        return JSONResponse(
            status_code=401, content={"detail": "missing or invalid caller key"}
        )


app = FastAPI(
    title="TradingCenter · capital-gateway",
    description=(
        "capital.com gateway — trading, deep history and a live stream behind one "
        "contract. Demo environment only. Endpoints return neutral DTOs; provider "
        "quirks (session tokens, the instrument tree, asynchronous settlement) stay "
        "inside the adapter. The WebSocket at /ws/stream is not described by this "
        "schema — see the module README."
    ),
    version="0.1.0",
    lifespan=lifespan,
    # A published schema hands anyone the exact shape of /orders and /positions/{id} — fine for a
    # developer who already has the source, not on the endpoint reachable from the internet.
    docs_url="/docs" if not is_production() else None,
    openapi_url="/openapi.json" if not is_production() else None,
)
app.add_middleware(GatewayDoor)


@app.exception_handler(GatewayError)
async def _gateway_error_handler(request: Request, exc: GatewayError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


def adapter(request: Request) -> CapitalAdapter:
    return request.app.state.adapter


def hub(websocket: WebSocket) -> Hub:
    return websocket.app.state.hub


@app.get("/", tags=["meta"])
async def root() -> dict:
    """The health probe. The one route reachable with no caller key, so it MUST NOT
    say anything beyond "this process is up" — no account, no session state, no route
    list, nothing a caller couldn't already have inferred by finding the module."""
    return {"service": "capital-gateway", "status": "ok"}


@app.get("/capabilities", tags=["meta"], response_model=Capabilities)
async def capabilities(a: CapitalAdapter = Depends(adapter)):
    """What this module serves, and which environment it is bound to."""
    return a.capabilities()



@app.get("/accounts", tags=["accounts"], response_model=list[Account])
async def accounts(a: CapitalAdapter = Depends(adapter)):
    return await a.list_accounts()


class SetActiveAccount(BaseModel):
    account_id: str = Field(description="an id from GET /accounts")


@app.put("/accounts/active", tags=["accounts"], response_model=Account)
async def set_active_account(body: SetActiveAccount, a: CapitalAdapter = Depends(adapter)):
    """Switch the active account. Positions and orders act on it afterwards.

    **Switching drops the quote stream.** capital.com ends the streaming session when the
    financial account changes, so anything collecting candles through `/ws/quotes` sees a
    disconnect and reconnects on its own — a gap of seconds, in data nobody is watching at
    the moment of the switch. Said here because this route answers success while the
    consequence lands somewhere else entirely.
    """
    return await a.set_active_account(body.account_id)


class TopUp(BaseModel):
    amount: float = Field(
        description=(
            "how much to move the demo balance by; negative takes funds away, which is "
            "as much a way of setting up an experiment as adding them. The provider's "
            "own limits — the balance ceiling, the range and the daily count — are its "
            "own, and a refusal names them."
        )
    )


@app.post("/accounts/top-up", tags=["accounts"], response_model=Account)
async def top_up(body: TopUp, a: CapitalAdapter = Depends(adapter)):
    """Move the demo account's balance, and answer with the account as it stands after.

    Acts on the **active** account — there is no account id to pass, because capital.com
    adjusts the session's own account and a parameter here would promise a choice that
    does not exist. Switch first if the money belongs somewhere else.
    """
    if body.amount == 0:
        raise HTTPException(422, detail="amount must not be zero")
    return await a.top_up(body.amount)



@app.get("/asset-classes", tags=["market-data"], response_model=list[AssetClass])
async def asset_classes() -> list[AssetClass]:
    """The classes this module describes instruments with.

    Published so a consumer offering a choice of class does not carry its own copy of
    the list — a copy is a thing that drifts, and it drifts silently.
    """
    return list(AssetClass)


# How much of the tree an unfiltered walk visits, and how much a filtered one may: one class is a
# fraction of the catalogue, and a consumer picking what to archive decides on what it can see.
_CATALOGUE_NODES = 300
_CLASS_NODES = 1500


@app.get("/instruments", tags=["market-data"], response_model=InstrumentPage)
async def instruments(
    max_nodes: int | None = Query(
        None,
        ge=1,
        le=5000,
        description="how much of the tree to walk; defaults higher when asset_class is set",
    ),
    asset_class: str | None = Query(
        None, description="narrow to one class, e.g. 'CRYPTO'; see GET /asset-classes"
    ),
    a: CapitalAdapter = Depends(adapter),
):
    """Every instrument, deduped. `truncated` is true when the bound cut the walk short."""
    wanted = _asset_class_or_refuse(asset_class)
    bound = max_nodes if max_nodes is not None else (_CLASS_NODES if wanted else _CATALOGUE_NODES)
    return await a.list_instruments(bound, wanted)


def _asset_class_or_refuse(value: str | None) -> AssetClass | None:
    """Read the query parameter, or refuse in a sentence naming the alternatives. Typed as `str`
    rather than the enum so the refusal is ours: the framework's would be a validation envelope."""
    if value is None:
        return None
    try:
        return AssetClass(value.strip().upper())
    except ValueError:
        known = ", ".join(c.value for c in AssetClass)
        raise GatewayError(
            f"unknown asset class {value!r}; this module knows {known}", status_code=422
        ) from None


@app.get("/instruments/search", tags=["market-data"], response_model=list[Instrument])
async def search_instruments(
    q: str = Query(..., description="e.g. 'gold', 'apple', 'btc'"),
    a: CapitalAdapter = Depends(adapter),
):
    return await a.search_instruments(q)


@app.get("/instruments/{symbol}/terms", tags=["market-data"], response_model=InstrumentTerms)
async def instrument_terms(
    symbol: str,
    a: CapitalAdapter = Depends(adapter),
):
    """The deposit and size rules for one instrument — no price; that is `/search` and
    `/candles`. A field the provider omits comes back null rather than as a default."""
    return await a.get_instrument_terms(symbol)


@app.get("/instruments/{symbol}/candles", tags=["market-data"], response_model=list[Candle])
async def candles(
    symbol: str,
    resolution: Resolution = Query(Resolution.MINUTE, description="candle time frame"),
    limit: int = Query(100, ge=1, le=1000, description="the provider's ceiling is 1000"),
    a: CapitalAdapter = Depends(adapter),
):
    """One request's worth of candles. For more than 1000, use `/history`."""
    return await a.get_candles(symbol, resolution, limit)


@app.get("/instruments/{symbol}/history", tags=["market-data"], response_model=CandleHistory)
async def history(
    request: Request,
    symbol: str,
    resolution: Resolution = Query(Resolution.MINUTE_5),
    bars: int = Query(1000, ge=1, le=50_000, description="how many candles to reach back for"),
    before: datetime | None = Query(
        None,
        description=(
            "reach back from this instant instead of now, so a window that ended in the "
            "past can be requested directly"
        ),
    ),
    after: datetime | None = Query(
        None,
        description=(
            "stop here: no candle older than this is fetched or returned. `bars` counts "
            "candles, so for an instrument that is not open around the clock it spans "
            "more calendar time than it looks — this is the only way to name a lower "
            "bound in time rather than in candles"
        ),
    ),
    a: CapitalAdapter = Depends(adapter),
):
    """Candles paged past the provider's per-request ceiling.

    This is a long request by design — 20 000 five-minute candles measured at 30 provider
    calls and 26 seconds. The response says how many requests it took, and paging stops
    early if the client disconnects.
    """

    async def still_wanted() -> bool:
        return not await request.is_disconnected()

    return await a.get_history(symbol, resolution, bars, still_wanted, anchor=before, floor=after)



@app.get("/positions", tags=["trading"], response_model=list[Position])
async def positions(a: CapitalAdapter = Depends(adapter)):
    return await a.list_positions()


@app.post("/orders", tags=["trading"], response_model=Order)
async def place_order(req: PlaceOrderRequest, a: CapitalAdapter = Depends(adapter)):
    """Place an order. MARKET fills now (FILLED); LIMIT and STOP rest (WORKING).

    The answer is settled, not acknowledged. A deal the provider has not resolved comes
    back PENDING with its reference — never FILLED.
    """
    return await a.place_order(req)


@app.delete("/positions/{position_id}", tags=["trading"], response_model=Order)
async def close_position(position_id: str, a: CapitalAdapter = Depends(adapter)):
    return await a.close_position(position_id)


@app.put("/positions/{position_id}", tags=["trading"], response_model=Order)
async def update_position(
    position_id: str, req: UpdatePositionRequest, a: CapitalAdapter = Depends(adapter)
):
    """Set or remove stops. A number sets, `null` removes, an omitted field is left
    alone — so amending one stop cannot clear the other."""
    return await a.update_position(position_id, req)


@app.get("/working-orders", tags=["trading"], response_model=list[WorkingOrder])
async def working_orders(a: CapitalAdapter = Depends(adapter)):
    """Resting LIMIT and STOP orders on the active account."""
    return await a.list_working_orders()


@app.delete("/working-orders/{order_id}", tags=["trading"], response_model=Order)
async def cancel_working_order(order_id: str, a: CapitalAdapter = Depends(adapter)):
    return await a.cancel_working_order(order_id)


# The stream is not described by the OpenAPI schema — OpenAPI has no vocabulary for WebSocket
# payloads. The message shapes are pydantic models in stream/messages.py.


@app.websocket("/ws/stream")
async def stream(websocket: WebSocket, the_hub: Hub = Depends(hub)) -> None:
    """Live candles and quotes for one symbol at one resolution. Reads nothing: the subscription
    is the query string, so there is no client protocol to get wrong."""
    # HTTP middleware never sees a WebSocket handshake, so the key is checked here, before
    # accept() — accepting and closing after would register the caller with the hub in between.
    expected: str = websocket.app.state.settings.gateway_api_key
    provided = websocket.headers.get(API_KEY_HEADER, "")
    # See GatewayDoor.dispatch above: compared as bytes so a non-ASCII header
    # cannot turn a refused handshake into an unhandled exception.
    if not provided or not hmac.compare_digest(provided.encode(), expected.encode()):
        await websocket.close(code=4401, reason="missing or invalid caller key")
        return

    symbol = (websocket.query_params.get("symbol") or "").strip().upper()
    raw_resolution = websocket.query_params.get("resolution") or Resolution.MINUTE_5.value

    if not symbol:
        # Refused before accepting. Accepting and then closing would look to a client
        # like a feed that died rather than a request that was wrong.
        await websocket.close(code=1008, reason="symbol is required")
        return
    try:
        resolution = Resolution(raw_resolution)
    except ValueError:
        await websocket.close(code=1008, reason=f"unknown resolution {raw_resolution!r}")
        return

    await websocket.accept()

    async def send(message) -> None:
        await websocket.send_json(message.model_dump(mode="json"))

    await the_hub.subscribe(symbol, resolution, send)
    try:
        # Nothing to read, but the receive keeps the connection open and is how a
        # disconnect is noticed — without it the handler returns and the socket closes.
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await the_hub.unsubscribe(symbol, resolution, send)
