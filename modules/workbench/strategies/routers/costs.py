"""The cost profile of each instrument: read off the broker when a run first needs one, changed here by the operator or
read off the broker again on request — no tool reaches it (design D6)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path

from .. import broker_costs, costs_store, margins
from ..archive import ArchiveUnavailable
from ..contract import CostProfileOut, MarginIn, MarginOut
from ..costs import CostModel
from .deps import archive, not_found, pool

router = APIRouter(tags=["costs"])

SYMBOL = Path(min_length=1, max_length=64, description="the instrument, as the archive names it")


def _out(profile: costs_store.Profile) -> CostProfileOut:
    return CostProfileOut.model_validate(profile.__dict__)


@router.get("/costs", response_model=list[CostProfileOut])
async def list_profiles(db=Depends(pool)) -> list[CostProfileOut]:
    async with db.acquire() as conn:
        return [_out(p) for p in await costs_store.list_all(conn)]


@router.get("/costs/{symbol}", response_model=CostProfileOut, responses={404: {}})
async def get_profile(symbol: str = SYMBOL, db=Depends(pool)) -> CostProfileOut:
    async with db.acquire() as conn:
        found = await costs_store.get(conn, symbol)
    if found is None:
        raise not_found(f"a cost profile for {symbol}")
    return _out(found)


@router.put("/costs/{symbol}", response_model=CostProfileOut)
async def put_profile(costs: CostModel, symbol: str = SYMBOL, db=Depends(pool)) -> CostProfileOut:
    """Replaces the profile with the operator's values. Runs already recorded keep the costs they were made with."""
    async with db.acquire() as conn:
        return _out(await costs_store.put(conn, symbol, costs))


@router.post(
    "/costs/{symbol}/from-broker", response_model=CostProfileOut,
    responses={
        422: {"description": "the broker's answer lacks a value the profile needs"},
        503: {"description": "the archive could not ask the broker"},
    },
)
async def profile_from_broker(symbol: str = SYMBOL, db=Depends(pool), reading=Depends(archive)) -> CostProfileOut:
    """Reads the profile off the broker now and replaces the one kept. Refused, with the profile unchanged, when the
    broker does not answer or leaves a value out."""
    try:
        read = await broker_costs.fetch(reading, symbol)
    except broker_costs.BrokerCostsMissing as err:
        raise HTTPException(status_code=422, detail=str(err)) from err
    except ArchiveUnavailable as err:
        raise HTTPException(status_code=503, detail=f"the broker's costs cannot be read now: {err}") from err
    async with db.acquire() as conn:
        return _out(await costs_store.put_from_broker(conn, symbol, read))


@router.get("/margins/{symbol}", response_model=MarginOut, responses={404: {}})
async def get_margin(symbol: str = SYMBOL, db=Depends(pool)) -> MarginOut:
    """The deposit a strategy sized by `margin_fraction` is computed with — read off the broker by its first run."""
    async with db.acquire() as conn:
        found = await margins.get(conn, symbol)
    if found is None:
        raise not_found(f"a deposit for {symbol}")
    return MarginOut.model_validate(found.__dict__)


@router.put("/margins/{symbol}", response_model=MarginOut)
async def put_margin(body: MarginIn, symbol: str = SYMBOL, db=Depends(pool)) -> MarginOut:
    """Replaces the deposit with the operator's. Runs already recorded keep the one they were made with."""
    async with db.acquire() as conn:
        return MarginOut.model_validate((await margins.put(conn, symbol, body.margin_factor)).__dict__)
