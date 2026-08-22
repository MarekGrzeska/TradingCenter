"""What the platform decided, and why — the record an operator argues with."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query, Request

from .. import store
from ..contract import DecisionDetailOut, DecisionOut
from ..errors import StrategyError
from ..store import RecordedDecision

router = APIRouter()

# A page of decisions. High enough that "what happened today" is one request for a strategy
# on hourly bars, low enough that nobody accidentally asks for a year of them.
DEFAULT_LIMIT = 100
MAX_LIMIT = 1_000


def _out(row: RecordedDecision) -> DecisionOut:
    return DecisionOut(
        id=row.id,
        strategy_id=row.strategy_id,
        symbol=row.symbol,
        parameter_set_id=row.parameter_set_id,
        as_of=row.as_of,
        action=row.decision.action,
        reason=row.decision.reason,
        reason_kind=row.reason_kind,
        direction=row.decision.direction,
        entry=row.decision.entry,
        stop=row.decision.stop,
        target=row.decision.target,
        rr=row.decision.rr,
        score=row.decision.score,
        features=dict(row.decision.features),
        created_at=row.created_at,
    )


@router.get("/decisions", tags=["decisions"])
async def list_decisions(
    request: Request,
    strategy_id: str | None = None,
    symbol: str | None = None,
    action: Literal["trade", "no_trade"] | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
) -> list[DecisionOut]:
    """Newest first, with the reason on every row.

    The refusals are the ordinary case and are not filtered out by default: "the system has
    not traded in three weeks" is answered by reading them, and a list that showed only
    setups would answer it with silence.
    """
    async with request.app.state.pool.acquire() as conn:
        rows = await store.list_decisions(
            conn, strategy_id=strategy_id, symbol=symbol, action=action, limit=limit
        )
    return [_out(row) for row in rows]


@router.get("/decisions/{decision_id}", tags=["decisions"])
async def read_decision(request: Request, decision_id: int) -> DecisionDetailOut:
    """One decision with the readings it stood on — enough to re-decide it offline."""
    async with request.app.state.pool.acquire() as conn:
        row = await store.read_decision(conn, decision_id)
    if row is None:
        raise StrategyError(f"no decision with id {decision_id}")
    return DecisionDetailOut(**_out(row).model_dump(), facts=row.facts)
