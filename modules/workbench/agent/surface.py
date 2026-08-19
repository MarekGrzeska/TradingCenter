"""The conversation's routes, and the assembly of what they read.

Split out of what used to be this package's own `app.py` when the two modules became one
process: the FastAPI instance and the lifespan are `workbench/app.py`'s now, and what stays
here is everything that is *about the conversation* — which routers it publishes, and what
goes on `app.state.agent` for them to read.

`teams/surface.py` is the twin of this file, and the two never import each other
(`tests/test_layering.py`).
"""

from __future__ import annotations

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
    """What the conversation's routes read, under `app.state.agent`.

    A namespace rather than attributes straight on `app.state`, because the other surface
    has a `pool`, a `catalogue`, a `provider` and a `settings` of its own and they are not
    the same objects — the collision is the reason this class exists.
    """

    settings: Settings
    pool: asyncpg.Pool
    catalogue: ModelCatalogue
    provider: OpenAIProvider
    tool_server: Any
    # Holds a turn's background task for as long as it runs, so nothing collects it
    # mid-generation just because the request that started it ended (design.md, "Tura
    # modelu przeżywa rozłączenie wołającego").
    background_tasks: set = field(default_factory=set)


def include(app: FastAPI) -> None:
    """Every route this surface publishes, at the paths it has always published them.

    None of them moved: where the two surfaces collided it is the other one that took a
    prefix (`teams/surface.py`), because the conversation is the larger half of what the
    terminal calls.
    """
    app.include_router(models.router)
    app.include_router(sessions.router)
    app.include_router(usage.router)
    app.include_router(prompt.router)
    app.include_router(chart.router)
    app.include_router(drawings.router)
