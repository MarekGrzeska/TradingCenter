"""`GET /usage` — zużycie i koszt w podziale na model, sesję i czas
(specs/agent-usage, "Zużycie da się odczytać zbiorczo")."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request

from .. import store
from ..auth import current_principal
from ..contract import UsageAggregateOut, UsageSummaryOut

router = APIRouter()


@router.get("/usage")
async def get_usage(
    request: Request,
    owner: str = Depends(current_principal),
    since: datetime | None = Query(None, alias="from"),
    until: datetime | None = Query(None, alias="to"),
) -> UsageSummaryOut:
    async with request.app.state.pool.acquire() as conn:
        by_model = await store.usage_by_model(conn, owner_principal=owner, since=since, until=until)
        by_session = await store.usage_by_session(
            conn, owner_principal=owner, since=since, until=until
        )
        by_day = await store.usage_by_day(conn, owner_principal=owner, since=since, until=until)
        total_cost = await store.usage_total_cost(
            conn, owner_principal=owner, since=since, until=until
        )
    return UsageSummaryOut(
        total_cost=str(total_cost),
        by_model=[UsageAggregateOut.from_aggregate(a) for a in by_model],
        by_session=[UsageAggregateOut.from_aggregate(a) for a in by_session],
        by_day=[UsageAggregateOut.from_aggregate(a) for a in by_day],
    )
