"""The teams routes, and the assembly of what they read — split out when the two modules became one process, with
`agent/surface.py` as its twin. `GET /models` and `GET /usage` existed on both with different answers, so these moved."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import asyncpg
from fastapi import FastAPI

from .config import Settings
from .models_catalogue import ModelCatalogue
from .provider import OpenAIProvider
from .routers import catalogue, memory, models, runs, schedules, usage
from .routers import tools as tools_router
from .runner import RunRegistry


@dataclass
class State:
    """What this surface's routes read, under `app.state.teams`."""

    settings: Settings
    pool: asyncpg.Pool
    catalogue: ModelCatalogue
    provider: OpenAIProvider
    tools: Any
    # The runs this process is working on, and who is watching each. In memory on purpose: the plan runs
    # exactly one worker, and the start-up sweep is what covers what this cannot.
    runs: RunRegistry
    clock: Any = None
# No `announced_tools` beside `tools`, and that is the point of the session: what the tool server publishes
# is asked of it when a definition is saved, never copied onto app state, where it would be stale.


def include(app: FastAPI) -> None:
    """Every route this surface publishes. Order is load-bearing on the first two lines: `/teams/models` and
    `/teams/usage` also match `/teams/{team_id}`, and the literal only wins by being registered first."""
    app.include_router(models.router, prefix="/teams")
    app.include_router(usage.router, prefix="/teams")
    app.include_router(catalogue.router)
    app.include_router(memory.router)
    app.include_router(runs.router)
    app.include_router(schedules.router)
    app.include_router(tools_router.router)
