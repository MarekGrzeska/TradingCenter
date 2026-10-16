"""What the gateway has been asked to say, and who hears it. Purposes are observed rather than declared, and
assignments are the operator's: REST alone, so a conversation that could re-point alerts could re-point them
at whoever it had been talking to.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status
from tc_runtime.caller_access import IN_PROCESS_CALLER

from .. import purposes, store
from ..contract import (
    AssignmentOut,
    AssignRequest,
    DescribePurposeRequest,
    Problem,
    PurposeOut,
)
from ..errors import GatewayError
from . import deps

router = APIRouter(tags=["purposes"])


@router.get("/purposes", response_model=list[PurposeOut])
async def list_purposes(request: Request) -> list[PurposeOut]:
    """Every purpose seen or announced, with the destination that hears it today and the assignment
    that decides it. Two reads and a loop in memory: the screen shows all of them at once."""
    async with deps.connection(request.app.state.pool) as conn:
        seen = await store.list_purposes(conn)
        assigned = await store.list_assignments(conn)
    by_key = {a.key: d for a, d in assigned}
    out: list[PurposeOut] = []
    for one in seen:
        key = purposes.deciding_key(one.name, frozenset(by_key))
        out.append(
            PurposeOut(
                name=one.name,
                description=one.description,
                first_seen=one.first_seen,
                last_seen=one.last_seen,
                last_caller=one.last_caller,
                destination=by_key[key].name if key else None,
                assigned_by=key,
            )
        )
    return out


@router.put(
    "/purposes/{name}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={422: {"model": Problem}},
)
async def announce(request: Request, name: str, body: DescribePurposeRequest) -> Response:
    """Announces a purpose with a description, before the first event: it is in the terminal, ready to be
    assigned. A purpose already known keeps its history and takes the new description."""
    try:
        purposes.valid_purpose(name)
    except GatewayError as err:
        raise deps.refusal(err) from err
    async with deps.connection(request.app.state.pool) as conn:
        await store.note_purpose(
            conn,
            name,
            caller=request.scope.get(IN_PROCESS_CALLER),
            description=body.description,
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/assignments", response_model=list[AssignmentOut])
async def list_assignments(request: Request) -> list[AssignmentOut]:
    async with deps.connection(request.app.state.pool) as conn:
        names = {bot.id: bot.username for bot in await store.list_bots(conn)}
        found = await store.list_assignments(conn)
    return [
        AssignmentOut(key=a.key, destination=d.name, bot=names[d.bot_id], receives=d.receives)
        for a, d in found
    ]


@router.put(
    "/assignments/{key}",
    response_model=AssignmentOut,
    responses={404: {"model": Problem}, 422: {"model": Problem}},
)
async def assign(request: Request, key: str, body: AssignRequest) -> AssignmentOut:
    """Points a purpose, a prefix of one, or `*` at a destination, replacing whatever it pointed at. In effect
    from the next message: nothing is cached."""
    try:
        purposes.valid_key(key)
    except GatewayError as err:
        raise deps.refusal(err) from err
    async with deps.connection(request.app.state.pool) as conn:
        destination = await store.destination_by_name(conn, body.destination)
        if destination is None:
            raise deps.not_found(f"{body.destination!r} is not a destination this gateway knows")
        await store.assign(conn, key=key, destination_id=destination.id)
        bot = await store.bot_by_id(conn, destination.bot_id)
    assert bot is not None  # a destination cannot outlive its bot
    return AssignmentOut(
        key=key, destination=destination.name, bot=bot.username, receives=destination.receives
    )


@router.delete(
    "/assignments/{key}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": Problem}},
)
async def unassign(request: Request, key: str) -> Response:
    async with deps.connection(request.app.state.pool) as conn:
        if not await store.unassign(conn, key):
            raise deps.not_found(f"{key!r} is not assigned")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
