"""What this gateway can do at all — read before concluding it is broken.

A gateway with no destination refuses every send, and so does one whose database is gone. This route
is the only thing that tells those apart from outside, which is why it answers with zeroes rather
than with a refusal when there is nothing here yet.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from .. import store
from ..contract import StateOut
from . import deps

router = APIRouter(tags=["meta"])


@router.get("/state", response_model=StateOut)
async def state(request: Request) -> StateOut:
    """Whether bots can be created, how many there are, and how many destinations receive."""
    settings = request.app.state.settings
    async with deps.connection(request.app.state.pool) as conn:
        return StateOut(
            account_session_configured=settings.can_create_bots,
            bots=await store.count_bots(conn),
            destinations=await store.count_destinations(conn),
            destinations_ready=await store.count_destinations(conn, receiving=True),
        )
