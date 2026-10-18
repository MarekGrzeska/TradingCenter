"""How the package stands. The one route that answers 'is it working?' rather than 'what did you find?'."""

from __future__ import annotations

from fastapi import APIRouter, Request

from .. import known, store
from ..contract import ClockOut, StateOut
from . import deps

router = APIRouter(tags=["state"])


@router.get("/state", response_model=StateOut)
async def state(request: Request) -> StateOut:
    app_state = request.app.state
    recipients = await known.recipients_if_possible(app_state)
    async with deps.connection(app_state.pool) as conn:
        standing = await store.standing(conn)
        named = await store.destinations_in_use(conn)
    # A recipient who is gone is a defect on every rule that names one; counted from the names, so a single recipient
    # missing from the door is one number and not a read of every rule.
    gone = 0 if recipients is None else len(named - recipients)
    beat = app_state.heartbeats["clock"]
    return StateOut(
        rules_enabled=standing["enabled"],
        rules_disabled=standing["disabled"],
        rules_with_defects=max(standing["drifted"], gone),
        waiting_fires=standing["waiting"],
        event_types=standing["event_types"],
        delivering=app_state.gateway is not None,
        drafting=app_state.drafter is not None,
        reading_values=app_state.tools is not None,
        clock=ClockOut(ran=beat.has_run, age_seconds=round(beat.age_seconds(), 1), expected_seconds=beat.expected_seconds),
    )
