"""The catalogue, the parameter sets and the watches — everything the operator sets."""

from __future__ import annotations

from fastapi import APIRouter, Request

from .. import store
from ..catalogue import all_entries, check_facts_are_announced, get
from ..contract import (
    FactOut,
    ParameterSetIn,
    ParameterSetOut,
    ParamOut,
    StrategyOut,
    WatchIn,
    WatchOut,
    WatchPatch,
)
from ..errors import StrategyError
from ..spec import StrategySpec

router = APIRouter()


def _out(spec: StrategySpec) -> StrategyOut:
    return StrategyOut(
        id=spec.id,
        name=spec.name,
        description=spec.description,
        resolution=spec.resolution,
        candles=spec.candles,
        facts=[
            FactOut(
                key=fact.name,
                indicator=fact.indicator,
                resolution=fact.resolution,
                params=dict(fact.params),
                bars=fact.bars,
            )
            for fact in spec.facts
        ],
        params=[
            ParamOut(
                name=param.name,
                type=param.type,
                default=param.default,
                min=param.min,
                max=param.max,
            )
            for param in spec.params
        ],
    )


@router.get("/strategies", tags=["catalogue"])
async def list_strategies() -> list[StrategyOut]:
    """Every strategy this image carries. Read from the catalogue, never from a table —
    the entries are code, and a row claiming otherwise would be a second truth."""
    return [_out(spec) for spec in all_entries()]


@router.get("/strategies/{strategy_id}", tags=["catalogue"])
async def read_strategy(strategy_id: str) -> StrategyOut:
    return _out(get(strategy_id))


@router.get("/parameter-sets", tags=["catalogue"])
async def list_parameter_sets(request: Request, strategy_id: str | None = None) -> list[ParameterSetOut]:
    async with request.app.state.pool.acquire() as conn:
        rows = await store.list_parameter_sets(conn, strategy_id)
    return [ParameterSetOut(**vars(row)) for row in rows]


@router.post("/parameter-sets", tags=["catalogue"], status_code=201)
async def add_parameter_set(request: Request, body: ParameterSetIn) -> ParameterSetOut:
    """Write the next version of a strategy's parameters.

    Resolved before it is stored — defaults filled in, every value checked against its
    declared range — so what is written down is what would be used, not what was typed. A
    value out of range is refused here rather than discovered at the next evaluation.
    """
    spec = get(body.strategy_id)
    resolved = spec.resolve_params(body.params)
    async with request.app.state.pool.acquire() as conn:
        written = await store.add_parameter_set(conn, spec.id, resolved)
    return ParameterSetOut(**vars(written))


@router.get("/watches", tags=["watches"])
async def list_watches(request: Request, active_only: bool = False) -> list[WatchOut]:
    async with request.app.state.pool.acquire() as conn:
        rows = await store.list_watches(conn, active_only=active_only)
    return [WatchOut(**vars(row)) for row in rows]


@router.post("/watches", tags=["watches"], status_code=201)
async def put_watch(request: Request, body: WatchIn) -> WatchOut:
    """Start watching a pair with a strategy.

    **This is where a strategy is registered**, and where its facts are checked against
    what the archive actually announces. The check is made here rather than at import
    because the answer can only be had by asking — and an archive that cannot be asked
    means the registration is refused, not that it is waved through: registering a
    strategy whose facts may not exist is how a platform ends up watching nothing and
    saying nothing.
    """
    spec = get(body.strategy_id)
    check_facts_are_announced(spec, await request.app.state.archive.announced_indicators())

    async with request.app.state.pool.acquire() as conn:
        if body.parameter_set_id is None:
            parameters = await store.add_parameter_set(conn, spec.id, spec.resolve_params())
            parameter_set_id = parameters.id
        else:
            parameters = await store.read_parameter_set(conn, body.parameter_set_id)
            if parameters is None or parameters.strategy_id != spec.id:
                raise StrategyError(
                    f"parameter set {body.parameter_set_id} does not belong to {spec.id}"
                )
            parameter_set_id = parameters.id
        watch = await store.put_watch(conn, spec.id, body.symbol, parameter_set_id)
    return WatchOut(**vars(watch))


@router.patch("/watches/{watch_id}", tags=["watches"])
async def set_watch_active(request: Request, watch_id: int, body: WatchPatch) -> WatchOut:
    """The whole of the off switch. Deactivating one watch leaves every other running, and
    is the way back out of a strategy — no deployment, no restart."""
    async with request.app.state.pool.acquire() as conn:
        watch = await store.set_watch_active(conn, watch_id, body.active)
    if watch is None:
        raise StrategyError(f"no watch with id {watch_id}")
    return WatchOut(**vars(watch))
