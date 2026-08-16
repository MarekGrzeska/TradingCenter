"""`GET /models` — the catalogue a wybierak is built from, and nothing else
(specs/teams-models, "Katalog modeli wystarcza do zbudowania wybieraka")."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..contract import ModelOut

router = APIRouter()


@router.get("/models")
async def list_models(request: Request) -> list[ModelOut]:
    catalogue = request.app.state.catalogue
    return [ModelOut.from_entry(entry) for entry in catalogue.entries()]
