"""The indicator catalogue and computation, over HTTP. Everything else moved to
`indicators/service.py` when the tool surface gave it a second caller; what stays is this transport."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..contract import (
    IndicatorsCatalogueOut,
    IndicatorsOut,
    IndicatorsRequest,
    Problem,
)
from ..indicators import service
from .deps import indicator_limiter, pool

router = APIRouter()


@router.get(
    "/indicators",
    tags=["indicators"],
    response_model=IndicatorsCatalogueOut,
    summary="Every indicator this module can compute, and how to draw it",
    description=(
        "A consumer builds its whole picker from this — parameters, defaults, output "
        "shape, render hint — and never needs to know an indicator by name beforehand."
    ),
)
async def catalogue() -> IndicatorsCatalogueOut:
    return service.catalogue()


@router.post(
    "/indicators/{symbol}",
    tags=["indicators"],
    response_model=IndicatorsOut,
    responses={422: {"model": Problem}},
    summary="Compute one or more indicators over a range, on one shared time axis",
    description=(
        "Reads further back than `from` on its own, by however much each requested "
        "indicator's warmup needs, and says in `warmup_from`/`settled` whether the "
        "archive actually held enough history for the answer to be trusted."
    ),
)
async def compute(
    symbol: str,
    body: IndicatorsRequest,
    db=Depends(pool),
    limiter=Depends(indicator_limiter),
) -> IndicatorsOut:
    try:
        return await service.compute(symbol, body, db, limiter)
    except service.IndicatorRequestRejected as rejected:
        raise HTTPException(status_code=422, detail=str(rejected)) from rejected
