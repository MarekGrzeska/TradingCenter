"""`GET /chart` — what the agent set the operator's chart to, global to the module. Nothing here writes: the cursor
belongs to the consumer, so two terminals cannot take a command away from each other."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from .. import store
from ..auth import current_principal
from ..contract import ChartCommandOut

router = APIRouter()


@router.get("/chart")
async def get_chart(
    request: Request,
    after: int = Query(
        default=0,
        ge=0,
        description="the sequence number the caller has already applied; 0 asks for the "
        "whole standing state",
    ),
    _: str = Depends(current_principal),
) -> ChartCommandOut | None:
    async with request.app.state.agent.pool.acquire() as conn:
        command = await store.chart_state_after(conn, sequence=after)
    # `null`, not an empty object: "nothing new" and "a command that sets nothing" would
    # otherwise read the same, and one of them cannot happen.
    return None if command is None else ChartCommandOut.from_command(command)
