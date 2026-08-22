"""Backtest runs that were kept — read only.

There is no route that *starts* one. A run over years of bars is minutes of work and would
hold a request open for all of it, so the backtest is a command (`python -m
strategy.backtest`) and this is where its reports are read back. That split is also what
keeps a long run from being something a caller can set off by accident.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from .. import store
from ..contract import BacktestRunOut
from ..errors import StrategyError

router = APIRouter()

MAX_LIMIT = 200


@router.get("/backtests", tags=["backtests"])
async def list_backtests(
    request: Request,
    strategy_id: str | None = None,
    limit: int = Query(50, ge=1, le=MAX_LIMIT),
) -> list[BacktestRunOut]:
    async with request.app.state.pool.acquire() as conn:
        rows = await store.list_backtest_runs(conn, strategy_id=strategy_id, limit=limit)
    return [BacktestRunOut(**vars(row)) for row in rows]


@router.get("/backtests/{run_id}", tags=["backtests"])
async def read_backtest(request: Request, run_id: int) -> BacktestRunOut:
    async with request.app.state.pool.acquire() as conn:
        row = await store.read_backtest_run(conn, run_id)
    if row is None:
        raise StrategyError(f"no backtest run with id {run_id}")
    return BacktestRunOut(**vars(row))
