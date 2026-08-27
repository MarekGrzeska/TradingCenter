"""The catalogue, the parameter sets and the watches — everything the operator sets. The catalogue is both
sources at once, and `source` on every row says which: a coded entry cannot be edited from a screen."""

from __future__ import annotations

from fastapi import APIRouter, Request

from .. import resolver, store
from ..catalogue import check_facts_are_announced
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
from ..errors import RevisionMismatch, StrategyError
from ..resolver import Resolved

router = APIRouter()


def _out(resolved: Resolved) -> StrategyOut:
    spec = resolved.spec
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
        source="code" if resolved.from_code else "revision",
        revision=None if resolved.revision is None else resolved.revision.version,
    )


@router.get("/strategies", tags=["catalogue"])
async def list_strategies(request: Request) -> list[StrategyOut]:
    """Every strategy this platform can run: the image's entries and the written rules.

    One list rather than two, because everything downstream treats them identically and a
    screen that had to merge two lists would be the first place the distinction leaked.
    """
    async with request.app.state.pool.acquire() as conn:
        return [_out(found) for found in await resolver.all_available(conn)]


@router.get("/strategies/{strategy_id}", tags=["catalogue"])
async def read_strategy(
    request: Request, strategy_id: str, revision: int | None = None
) -> StrategyOut:
    """One strategy, at a named revision or at its newest.

    `revision` on a coded entry is refused rather than ignored: it is a caller believing
    something untrue about which kind of strategy this is.
    """
    async with request.app.state.pool.acquire() as conn:
        return _out(await resolver.resolve(conn, strategy_id, version=revision))


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

    The set is stamped with the revision whose declaration it satisfied. Which ranges a set
    was checked against is a fact about the moment it was written, and one revision later it
    may not be true any more (design.md, decision 6).
    """
    async with request.app.state.pool.acquire() as conn:
        found = await resolver.resolve(conn, body.strategy_id)
        resolved = found.spec.resolve_params(body.params)
        written = await store.add_parameter_set(
            conn, found.spec.id, resolved, strategy_revision_id=found.revision_id
        )
    return ParameterSetOut(**vars(written))


@router.get("/watches", tags=["watches"])
async def list_watches(request: Request, active_only: bool = False) -> list[WatchOut]:
    async with request.app.state.pool.acquire() as conn:
        rows = await store.list_watches(conn, active_only=active_only)
    return [WatchOut(**vars(row)) for row in rows]


@router.post("/watches", tags=["watches"], status_code=201)
async def put_watch(request: Request, body: WatchIn) -> WatchOut:
    """Start watching a pair with a strategy, or move an existing watch.

    **This is where a strategy is registered**, and where its facts are checked against
    what the archive actually announces. The check is made here rather than at import
    because the answer can only be had by asking — and an archive that cannot be asked
    means the registration is refused, not that it is waved through: registering a
    strategy whose facts may not exist is how a platform ends up watching nothing and
    saying nothing. It stays here even though a written rule was already checked when it was
    saved: the archive's catalogue can change in between, and this is the check that guards
    the loop (design.md, decision 8).

    **The revision is pinned, not followed.** Omitting `revision` pins the newest at this
    moment; a revision written afterwards changes nothing about this watch until somebody
    calls here again.
    """
    async with request.app.state.pool.acquire() as conn:
        found = await resolver.resolve(conn, body.strategy_id, version=body.revision)
        check_facts_are_announced(
            found.spec, await request.app.state.archive.announced_indicators()
        )

        if body.parameter_set_id is None:
            parameters = await store.add_parameter_set(
                conn,
                found.spec.id,
                found.spec.resolve_params(),
                strategy_revision_id=found.revision_id,
            )
        else:
            parameters = await store.read_parameter_set(conn, body.parameter_set_id)
            if parameters is None or parameters.strategy_id != found.spec.id:
                raise StrategyError(
                    f"parameter set {body.parameter_set_id} does not belong to {found.spec.id}"
                )
            if parameters.strategy_revision_id != found.revision_id:
                # A value inside its range under one revision may be outside it — or have no
                # declaration at all — under the next.
                raise RevisionMismatch(
                    parameters.id, parameters.strategy_revision_id, found.revision_id
                )
        watch = await store.put_watch(
            conn,
            found.spec.id,
            body.symbol,
            parameters.id,
            strategy_revision_id=found.revision_id,
        )
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
