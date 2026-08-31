"""`GET /models` — the catalogue a wybierak is built from, and nothing else. The route body is
`tc_runtime.routers.models_router`; what this surface supplies is its own `ModelOut` and its catalogue."""

from __future__ import annotations

from tc_runtime.routers import models_router

from ..contract import ModelOut

router = models_router(ModelOut, lambda request: request.app.state.teams.catalogue)
