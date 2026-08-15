"""The published surface: FastAPI over the conversation.

Assembly only, same split as `market_data/app.py`: the lifespan and the routers mounted
onto it. Routes live in `routers/`, one file per area, as they arrive.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

# Root logger configuration, before anything else imports and starts logging. Nothing
# else sets a level or a destination — mirrors market_data.telemetry's reasoning:
# without this the module writes into the void, and a silent module looks exactly like
# an idle one.
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(levelname)-5.5s [%(name)s] %(message)s",
)

from fastapi import FastAPI

from .config import Settings
from .db import pool as make_pool
from .models_catalogue import ModelCatalogue
from .provider import OpenAIProvider
from .routers import models, prompt, sessions, usage
from .tools import ToolServer

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()  # type: ignore[call-arg]
    # Constructed, not connected: the session opens on the first turn that wants a tool.
    # Reaching market-mcp at startup would make this module's health depend on another
    # module's, and its whole answer to that module being down is to run without tools.
    tool_server = ToolServer(settings)
    async with make_pool(
        settings.database_url,
        user=settings.database_user,
        client_id=settings.azure_client_id,
        client_secret=settings.azure_client_secret,
        tenant_id=settings.azure_tenant_id,
    ) as pool:
        app.state.settings = settings
        app.state.pool = pool
        app.state.catalogue = ModelCatalogue.from_settings(settings)
        app.state.provider = OpenAIProvider(settings)
        app.state.tool_server = tool_server
        # Holds a turn's background task for as long as it runs, so nothing collects
        # it mid-generation just because the request that started it ended
        # (design.md, "Tura modelu przeżywa rozłączenie wołającego").
        app.state.background_tasks = set()
        try:
            yield
        finally:
            await tool_server.aclose()


app = FastAPI(
    title="TradingCenter · agent",
    description=(
        "The operator's conversation with a model. Sessions and their transcripts "
        "persist in this module's own database; each model call prices itself at the "
        "moment it is written, against the module's own rate configuration, never "
        "recomputed later. Read-only tools over the candle archive, reached through "
        "market-mcp — nothing here writes anywhere."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# No CORS middleware here, and adding one would break the browser rather than help it —
# same reasoning as market_data.app: App Service's own CORS layer answers the
# cross-origin preflight before Easy Auth would refuse it for carrying no credential.
# See infra/app-service.tf.


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(models.router)
app.include_router(sessions.router)
app.include_router(usage.router)
app.include_router(prompt.router)
