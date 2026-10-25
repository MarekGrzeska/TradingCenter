"""The language, described from the registry the validator checks against — so the two cannot disagree."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from .. import language as described
from ..contract import LanguageOut
from .deps import archive

router = APIRouter(tags=["language"])


@router.get("/language", response_model=LanguageOut)
async def language(reading=Depends(archive)) -> LanguageOut:
    return await described.describe(reading)
