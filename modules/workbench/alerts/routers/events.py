"""What the packages of this process announce they can say. Announcing is theirs alone: see `deps.only_the_process`."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request, Response, status
from tc_runtime.caller_access import IN_PROCESS_CALLER

from .. import rules, store
from ..contract import EventTypeIn, Problem
from . import deps

log = logging.getLogger(__name__)

router = APIRouter(tags=["events"], dependencies=[Depends(deps.only_the_process)])


@router.put(
    "/event-types/{name}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={403: {"model": Problem}, 422: {"model": Problem}},
)
async def announce(request: Request, name: str, body: EventTypeIn) -> Response:
    """Says what an event of this type carries. Again, it replaces the schema — and every rule already written for the
    type is looked at once more, so one that named an attribute that is gone says so on the list instead of going quiet."""
    async with deps.connection(request.app.state.pool) as conn, conn.transaction():
        await store.upsert_event_type(
            conn,
            name,
            description=body.description,
            schema=body.schema_,
            announced_by=request.scope.get(IN_PROCESS_CALLER),
        )
        for row in await store.rules_of_event_type(conn, name):
            found = rules.drift(row, body.schema_)
            if found != row["defect"]:
                await store.set_defect(conn, row["id"], found)
                log.warning("rule %s no longer fits event type %s: %s", row["id"], name, found or "fits again")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
