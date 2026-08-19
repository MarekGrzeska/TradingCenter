"""Routes whose whole body was the same in two places.

`GET /models` is the only one so far: the conversation's and the teams surface's own
`routers/models.py` were 93.8% identical on 18 August 2026, differing in the spec they cite
and nothing else. It is a factory rather than a router, because the real differences are
arguments — the response type, since each surface publishes its own `ModelOut` and neither
should start publishing the other's, and where its catalogue is kept.

The second argument arrived when the two surfaces came to share one process: they hold
their state under separate names on the same application, so "read
`app.state.catalogue`" stopped being a fact this package could know.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Request


def models_router(model_out: type[Any], catalogue_of: Callable[[Request], Any]) -> APIRouter:
    """`GET /models` — the catalogue a wybierak is built from, and nothing else.

    `model_out` needs a `from_entry` classmethod taking one catalogue entry;
    `catalogue_of` returns the catalogue for a request, from wherever its caller keeps one.
    """
    router = APIRouter()

    @router.get("/models", response_model=list[model_out])
    async def list_models(request: Request):
        return [model_out.from_entry(entry) for entry in catalogue_of(request).entries()]

    return router
