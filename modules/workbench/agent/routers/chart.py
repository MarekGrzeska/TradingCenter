"""`GET /chart` — what the agent set the operator's chart to.

Global to the module, not scoped to an owner, for the same reason the prompt is: there is
one chart, and `current_principal` is asked only to refuse an unauthenticated request.

The consumer says what it has already applied and gets back either nothing or one command
carrying everything newer, folded (`store.chart_state_after`). Nothing here writes: the
cursor belongs to the consumer, so that two terminals, or one reopened, cannot take a
command away from each other (specs/agent-chart-control, "Konsument czyta tylko to, czego
jeszcze nie zastosował").
"""

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
    async with request.app.state.pool.acquire() as conn:
        command = await store.chart_state_after(conn, sequence=after)
    # `null`, not an empty object: "nothing new" and "a command that sets nothing" would
    # otherwise read the same, and one of them cannot happen.
    return None if command is None else ChartCommandOut.from_command(command)
