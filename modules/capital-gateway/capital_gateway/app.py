"""The published surface: FastAPI over the adapter, plus the streaming WebSocket."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .adapter import CapitalAdapter
from .client import CapitalClient
from .config import Settings
from .dtos import (
    Account,
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


def hub(request: Request) -> Hub:
    return request.app.state.hub


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


@app.get("/instruments", tags=["market-data"], response_model=InstrumentPage)
async def instruments(
    max_nodes: int = Query(300, ge=1, le=3000, description="how much of the tree to walk"),
    a: CapitalAdapter = Depends(adapter),
):
    """Every instrument, deduped. `truncated` is true when the bound cut the walk short."""
    return await a.list_instruments(max_nodes)


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
    a: CapitalAdapter = Depends(adapter),
):
    """Candles paged past the provider's per-request ceiling.

    This is a long request by design — 20 000 five-minute candles measured at 30 provider
    calls and 26 seconds. The response says how many requests it took, and paging stops
    early if the client disconnects.
    """

    async def still_wanted() -> bool:
        return not await request.is_disconnected()

    return await a.get_history(symbol, resolution, bars, still_wanted)


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
