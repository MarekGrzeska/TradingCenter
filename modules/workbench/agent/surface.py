"""The conversation's routes, and the assembly of what they read. Split out of this package's own `app.py`
when the two modules became one process: what stays is everything that is about the conversation.

`teams/surface.py` is the twin of this file, and the two never import each other."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import asyncpg
from fastapi import FastAPI

from .config import Settings
from .models_catalogue import ModelCatalogue
from .provider import OpenAIProvider
from .routers import chart, drawings, models, prompt, sessions, usage


@dataclass
class State:
    """What the conversation's routes read, under `app.state.agent`. A namespace rather than attributes
    straight on `app.state`: the other surface has a pool, a catalogue and a provider that are not these."""

    settings: Settings
    pool: asyncpg.Pool
    catalogue: ModelCatalogue
    provider: OpenAIProvider
    tool_server: Any
    # Holds a turn's background task for as long as it runs, so nothing collects it mid-generation just
    # because the request that started it ended.
    background_tasks: set = field(default_factory=set)
    # The turn running in each rozmowa, so the stop route can find the one the operator is looking at. In
    # this process and nowhere else, resting on one fact: this plan runs exactly one worker, on purpose.
    running_turns: dict[int, asyncio.Event] = field(default_factory=dict)


def include(app: FastAPI) -> None:
    """Every route this surface publishes, at the paths it has always published them. None of them moved:
    where the two surfaces collided it is the other one that took a prefix."""
    app.include_router(models.router)
    app.include_router(sessions.router)
    app.include_router(usage.router)
    app.include_router(prompt.router)
    app.include_router(chart.router)
    app.include_router(drawings.router)
