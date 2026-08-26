"""`GET /usage` — what a run or a team cost, broken down by agent, because a total tells nobody whether the expensive
part was the four cheap gatherers or the one dear judge. Nothing here computes a cost: every number is a `SUM`."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from .. import store
from ..auth import current_principal
from ..contract import UsageAggregateOut, UsageSummaryOut

router = APIRouter()


def _aggregate(row) -> UsageAggregateOut:
    return UsageAggregateOut(
        key=row["key"],
        input_tokens=row["input_tokens"],
        output_tokens=row["output_tokens"],
        cost=str(row["cost"]),
        unknown_count=row["unknown_count"],
    )


@router.get("/usage")
async def get_usage(
    request: Request,
    owner: str = Depends(current_principal),
    run_id: int | None = Query(None),
    team_id: int | None = Query(None),
) -> UsageSummaryOut:
    """Both filters are optional and combine. A run belonging to somebody else returns nothing rather than
    404 — this is an aggregate, and "no rows" versus "not yours" is exactly what a stranger must not tell."""
    async with request.app.state.teams.pool.acquire() as conn:
        by_agent = await store.usage_by_agent(
            conn, owner_principal=owner, run_id=run_id, team_id=team_id
        )
        by_model = await store.usage_by_model(
            conn, owner_principal=owner, run_id=run_id, team_id=team_id
        )
        total = await store.usage_total_cost(
            conn, owner_principal=owner, run_id=run_id, team_id=team_id
        )
    return UsageSummaryOut(
        total_cost=str(total),
        by_agent=[_aggregate(row) for row in by_agent],
        by_model=[_aggregate(row) for row in by_model],
    )
