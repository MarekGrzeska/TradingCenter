"""The published surface: FastAPI over the adapter, plus the streaming WebSocket."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from .adapter import CapitalAdapter
from .client import CapitalClient
from .config import Settings
from .dtos import Capabilities
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
