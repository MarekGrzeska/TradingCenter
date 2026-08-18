"""Routes whose whole body was the same in two modules.

`GET /models` is the only one so far: `agent/routers/models.py` and
`teams/routers/models.py` were 93.8% identical on 18 August 2026, differing in the spec
they cite and nothing else. It is a factory rather than a router, because the one real
difference is the response type — each module publishes its own `ModelOut` and neither
should start publishing the other's.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request


def models_router(model_out: type[Any]) -> APIRouter:
    """`GET /models` — the catalogue a wybierak is built from, and nothing else.

    Reads `request.app.state.catalogue`, which both modules set in their own lifespan;
    `model_out` needs a `from_entry` classmethod taking one catalogue entry.
    """
    router = APIRouter()

    @router.get("/models", response_model=list[model_out])
    async def list_models(request: Request):
        catalogue = request.app.state.catalogue
        return [model_out.from_entry(entry) for entry in catalogue.entries()]

    return router
