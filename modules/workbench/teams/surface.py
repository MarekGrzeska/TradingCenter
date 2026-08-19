"""The teams routes, and the assembly of what they read.

Split out of what used to be this package's own `app.py` when the two modules became one
process — see `agent/surface.py`, its twin, for the shape and for why neither imports the
other.

**Two paths moved and the rest did not.** `GET /models` and `GET /usage` existed on both
surfaces with different answers, so this one's are published under `/teams/`. Every other
route is exactly where it was.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import asyncpg
from fastapi import FastAPI

from .config import Settings
from .models_catalogue import ModelCatalogue
from .provider import OpenAIProvider
from .routers import catalogue, models, runs, schedules, usage
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
    # The runs this process is working on, and who is watching each. In memory on purpose:
    # the plan runs exactly one worker (`infra/app-service.tf`), and the start-up sweep in
    # `workbench/app.py` is what covers the case this cannot — a process that died with
    # runs in it.
    runs: RunRegistry
    clock: Any = None
    # No `announced_tools` beside `tools`, and that is the point of the session: what the
    # tool server publishes is asked of it at the moment a definition is saved
    # (`routers/catalogue._check`), never copied onto app state at start-up. A list kept
    # here would be a second copy of somebody else's catalogue, stale from the first tool
    # that server adds (specs/teams-tool-access).


def include(app: FastAPI) -> None:
    """Every route this surface publishes.

    **Order is load-bearing on the first two lines.** `/teams/models` and `/teams/usage`
    are literals that also match `/teams/{team_id}` in the catalogue router: Starlette
    matches a path segment as `[^/]+` before FastAPI tries to read it as an `int`, so the
    literal only wins by being registered first. `tests/test_route_collisions.py` is what
    keeps these two lines above the third one.
    """
    app.include_router(models.router, prefix="/teams")
    app.include_router(usage.router, prefix="/teams")
    app.include_router(catalogue.router)
    app.include_router(runs.router)
    app.include_router(schedules.router)
    app.include_router(tools_router.router)
