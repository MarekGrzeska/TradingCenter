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

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()  # type: ignore[call-arg]
    app.state.settings = settings
    yield


app = FastAPI(
    title="TradingCenter · agent",
    description=(
        "The operator's conversation with a model. Sessions and their transcripts "
        "persist in this module's own database; each model call prices itself at the "
        "moment it is written, against the module's own rate configuration, never "
        "recomputed later. No tools yet — a vertical slice the next changes build on."
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
