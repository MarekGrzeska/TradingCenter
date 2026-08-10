"""The published surface: FastAPI over the adapter, plus the streaming WebSocket.

Every route below is a trading endpoint or reads toward one, with one exception: `/`,
which the hosting platform polls with no credential to decide whether to restart the
process. That single exception is why the credential check is middleware rather than a
route dependency — a dependency would have to be added to every route by hand, and the
one route someone forgets is the one that ships open.
"""

from __future__ import annotations

import hmac
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

from . import telemetry
from .adapter import CapitalAdapter
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
    """The pair the streaming protocol needs, from a session known to still answer.

    The stream borrows the REST session and has no way of noticing that it stopped
    working: a websocket never receives a 401. `client.authenticated` says the tokens
    exist, not that the provider still honours them — and capital.com invalidates the
    previous session on every new login anywhere on the account, so one `-m live` run, or
    a second gateway process, leaves this one holding a pair of dead strings.

    Trusting them is a reconnect loop that never recovers. Every attempt subscribes with
    the same dead tokens, the provider refuses, the socket drops, and three seconds later
    it happens again — for as long as nothing else makes a REST call. Measured as a real
    hazard before running the live suite against the account production uses.

    So the session is *checked* here rather than assumed, through the one path that
    already heals itself: `request()` answers a 401 by logging in again and retrying, so
    by the time this returns the tokens are ones the provider has just accepted. One
    extra request per connection, and a connection is rare — the loop that would need
    this often is exactly the loop it exists to break.
    """
    await client.session_details()
    return client.stream_tokens()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Settings first, and outside a try: a live URL or a missing credential must stop
    # the process here rather than surface later as a failing request.
    # Before anything else that might have something to say. A failure in `Settings()`
    # below is exactly the kind of thing that has to be readable, and it is unreadable if
    # logging is configured after it.
    telemetry.configure()

    settings = Settings()  # type: ignore[call-arg]
    client = CapitalClient(settings)

    async def tokens() -> tuple[str, str]:
        return await stream_tokens_for(client)

    adapter = CapitalAdapter(client)

    async def current_period(epic: str, resolution: Resolution) -> Bar | None:
        """Where the period a room is currently building starts.

        Only asked for DAY and WEEK, whose boundary follows the venue's session rather
        than the clock, and only when nothing cheaper can answer. One candle: the
        provider's newest is the period it is in, and its stamp is the boundary this
        module is not allowed to compute.
        """
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
            settings.capital_stream_url, epic, resolution, tokens, emit
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


# The one route the hosting platform must reach with no credential, to decide whether
# to restart the process, plus the schema routes — a browser fetching /docs or
# /openapi.json carries no X-Gateway-Key, so without this exemption they 401 instead of
# serving the page they are meant to. Harmless in production: docs_url/openapi_url are
# None there, so FastAPI has no route registered at either path regardless of what this
# set exempts, and the request still ends in 404. Exact matches, not prefixes — a prefix
# match would be one typo away from exempting a real route.
_UNAUTHENTICATED_PATHS = frozenset({"/", "/docs", "/openapi.json"})


class RequireGatewayKey(BaseHTTPMiddleware):
    """Rejects every request but the health probe unless it carries the caller key.

    `hmac.compare_digest` rather than `==`: a plain comparison returns as soon as the
    first byte differs, and the time that takes leaks how many leading bytes a guess got
    right. That timing channel is exactly the kind of thing not worth having on a
    trading endpoint's front door.
    """

    async def dispatch(self, request: Request, call_next):
        if request.url.path in _UNAUTHENTICATED_PATHS:
            return await call_next(request)

        expected: str = request.app.state.settings.gateway_api_key
        provided = request.headers.get(API_KEY_HEADER, "")
        # Compared as bytes: hmac.compare_digest raises TypeError on a `str` containing a
        # non-ASCII character, and a header can carry one — encoding first turns a caller
        # sending garbage into the intended 401 instead of an unhandled 500.
        if not provided or not hmac.compare_digest(provided.encode(), expected.encode()):
            return JSONResponse(
                status_code=401, content={"detail": "missing or invalid caller key"}
            )

        return await call_next(request)


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
    # A published schema hands anyone the exact shape of /orders and /positions/{id}.
    # Fine off production, where the caller is a developer who already has the source;
    # not fine on the endpoint actually reachable from the internet.
    docs_url="/docs" if not is_production() else None,
    openapi_url="/openapi.json" if not is_production() else None,
)
app.add_middleware(RequireGatewayKey)


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


# --- accounts ---


@app.get("/accounts", tags=["accounts"], response_model=list[Account])
async def accounts(a: CapitalAdapter = Depends(adapter)):
    return await a.list_accounts()


class SetActiveAccount(BaseModel):
    account_id: str = Field(description="an id from GET /accounts")


@app.put("/accounts/active", tags=["accounts"], response_model=Account)
async def set_active_account(body: SetActiveAccount, a: CapitalAdapter = Depends(adapter)):
    """Switch the active account. Positions and orders act on it afterwards."""
    return await a.set_active_account(body.account_id)


# --- market data ---


@app.get("/asset-classes", tags=["market-data"], response_model=list[AssetClass])
async def asset_classes() -> list[AssetClass]:
    """The classes this module describes instruments with.

    Published so a consumer offering a choice of class does not carry its own copy of
    the list — a copy is a thing that drifts, and it drifts silently.
    """
    return list(AssetClass)


# How much of the tree an unfiltered walk visits, and how much a filtered one may. One
# class is a fraction of the catalogue, so the same budget spent looking for it reaches
# correspondingly further in — and a consumer picking an instrument to archive decides
# on what it can see, which makes a list cut short worse for it than for a browser.
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
    """Read the query parameter, or refuse in a sentence naming the alternatives.

    Typed as `str` on the route rather than as the enum so this refusal is ours: the
    framework's own would be a validation envelope about an unexpected literal, and the
    caller's next move is to pick a different class, which is exactly what the list
    below gives them.
    """
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


# --- trading ---


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


# --- streaming ---
#
# Not described by the OpenAPI schema — OpenAPI has no vocabulary for WebSocket
# payloads. The message shapes are pydantic models in stream/messages.py and are
# documented in the module README.


@app.websocket("/ws/stream")
async def stream(websocket: WebSocket, the_hub: Hub = Depends(hub)) -> None:
    """Live candles and quotes for one symbol at one resolution.

    Sends `candle` (forming and settled), `quote`, `status` and `error`. Reads nothing:
    the subscription is the query string, so there is no client protocol to get wrong.
    """
    # HTTP middleware never sees a WebSocket handshake, so the caller key is checked
    # here, before accept() — accepting first and closing after would register the
    # caller with the hub for the instant between the two.
    expected: str = websocket.app.state.settings.gateway_api_key
    provided = websocket.headers.get(API_KEY_HEADER, "")
    # See RequireGatewayKey.dispatch above: compared as bytes so a non-ASCII header
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
