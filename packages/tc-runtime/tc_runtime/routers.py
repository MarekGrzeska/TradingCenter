"""Routes whose whole body was the same in two places. A factory rather than a router, because the real
differences are arguments: the response type each surface publishes, and where its catalogue is kept."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Request


def models_router(model_out: type[Any], catalogue_of: Callable[[Request], Any]) -> APIRouter:
    """`GET /models` — the catalogue a wybierak is built from, and nothing else. `model_out` needs a
    `from_entry` classmethod; `catalogue_of` returns the catalogue for a request."""
    router = APIRouter()

    @router.get("/models", response_model=list[model_out])
    async def list_models(request: Request):
        return [model_out.from_entry(entry) for entry in catalogue_of(request).entries()]

    return router
