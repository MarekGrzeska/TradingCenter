"""The published surface: FastAPI over the adapter, plus the streaming WebSocket."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .adapter import CapitalAdapter
from .client import CapitalClient
from .config import Settings
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
from .stream.hub import Hub
from .stream.upstream import Upstream


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Settings first, and outside a try: a live URL or a missing credential must stop
    # the process here rather than surface later as a failing request.
    settings = Settings()  # type: ignore[call-arg]
    client = CapitalClient(settings)

    async def tokens() -> tuple[str, str]:
        # The stream has no credential of its own — it borrows the REST session, which
        # is why a login is forced before the first connection rather than after it.
        if not client.authenticated:
            await client.login()
        return client.stream_tokens()

    hub = Hub(
        lambda epic, resolution, emit: Upstream(
            settings.capital_stream_url, epic, resolution, tokens, emit
        )
    )

    app.state.settings = settings
    app.state.client = client
    app.state.adapter = CapitalAdapter(client)
    app.state.hub = hub
    try:
        yield
    finally:
        await hub.aclose()
        await client.aclose()


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
)


@app.exception_handler(GatewayError)
async def _gateway_error_handler(request: Request, exc: GatewayError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


def adapter(request: Request) -> CapitalAdapter:
    return request.app.state.adapter


def hub(websocket: WebSocket) -> Hub:
    return websocket.app.state.hub


@app.get("/", tags=["meta"])
async def root() -> dict:
    return {"service": "capital-gateway", "provider": "capital.com", "docs": "/docs"}


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
