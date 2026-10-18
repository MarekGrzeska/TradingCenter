"""How the package stands. The one route that answers 'is it working?' rather than 'what did you find?'."""

from __future__ import annotations

from fastapi import APIRouter, Request

from .. import known, reach, store
from ..contract import ClockOut, StateOut
from . import deps

router = APIRouter(tags=["state"])


@router.get("/state", response_model=StateOut)
async def state(request: Request) -> StateOut:
    app_state = request.app.state
    recipients = await known.recipients_if_possible(app_state)
    async with deps.connection(app_state.pool) as conn:
        standing = await store.standing(conn)
        # A recipient who is gone, a bot the recipient is not reached through, and a recipient with several bots and a
        # rule that did not choose are each a defect of the rule, counted once per rule.
        defective = sum(
            1
            for row in await store.rule_targets(conn)
            if row["defect"] is not None or reach.defect_of(row["destination"], row["bot"], recipients) is not None
        )
    beat = app_state.heartbeats["clock"]
    return StateOut(
        rules_enabled=standing["enabled"],
        rules_disabled=standing["disabled"],
        rules_with_defects=defective,
        waiting_fires=standing["waiting"],
        event_types=standing["event_types"],
        delivering=app_state.gateway is not None,
        drafting=app_state.drafter is not None,
        reading_values=app_state.tools is not None,
        clock=ClockOut(ran=beat.has_run, age_seconds=round(beat.age_seconds(), 1), expected_seconds=beat.expected_seconds),
    )
