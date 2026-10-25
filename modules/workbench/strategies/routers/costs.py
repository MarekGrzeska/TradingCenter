"""The cost profile of each instrument: set by the operator here and nowhere else — no tool reaches it (design D6)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path

from .. import costs_store
from ..contract import CostProfileOut
from ..costs import CostModel
from .deps import not_found, pool

router = APIRouter(tags=["costs"])

SYMBOL = Path(min_length=1, max_length=64, description="the instrument, as the archive names it")


@router.get("/costs", response_model=list[CostProfileOut])
async def list_profiles(db=Depends(pool)) -> list[CostProfileOut]:
    async with db.acquire() as conn:
        return [CostProfileOut.model_validate(p.__dict__) for p in await costs_store.list_all(conn)]


@router.get("/costs/{symbol}", response_model=CostProfileOut, responses={404: {}})
async def get_profile(symbol: str = SYMBOL, db=Depends(pool)) -> CostProfileOut:
    async with db.acquire() as conn:
        found = await costs_store.get(conn, symbol)
    if found is None:
        raise not_found(f"a cost profile for {symbol}")
    return CostProfileOut.model_validate(found.__dict__)


@router.put("/costs/{symbol}", response_model=CostProfileOut)
async def put_profile(costs: CostModel, symbol: str = SYMBOL, db=Depends(pool)) -> CostProfileOut:
    """Replaces the profile. Runs already recorded keep the costs they were made with."""
    async with db.acquire() as conn:
        return CostProfileOut.model_validate((await costs_store.put(conn, symbol, costs)).__dict__)
