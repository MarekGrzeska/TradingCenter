"""Observation groups — this module's own categories, not the provider's tags. A tag describes the
public database; a group describes what we watch, and the two acts are different."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator

from .. import store
from ..contract import GroupOut, Problem
from ..models import Group
from . import deps

router = APIRouter(tags=["groups"])


class GroupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("a group needs a name that is not only spaces")
        return value


class AssignRequest(BaseModel):
    group_id: int | None = Field(
        default=None, description="null takes the event out of every group without untracking it"
    )


@router.get("/groups", response_model=list[GroupOut])
async def list_groups(request: Request) -> list[GroupOut]:
    async with deps.connection(request.app.state.pool) as conn:
        groups = await store.list_groups(conn)
    return [_out(group) for group in groups]


@router.post("/groups", response_model=GroupOut, status_code=status.HTTP_201_CREATED)
async def create_group(request: Request, body: GroupRequest) -> GroupOut:
    """Idempotent on the name in any case or spacing: asking twice for the same category answers the one that
    exists, and "Crypto" is the group "crypto" already is."""
    async with deps.connection(request.app.state.pool) as conn:
        group, _ = await store.create_group(conn, body.name)
        found = await store.find_group(conn, group.name)
    return _out(found or group)


@router.patch(
    "/groups/{group_id}", response_model=GroupOut,
    responses={404: {"model": Problem}, 409: {"model": Problem}},
)
async def rename_group(request: Request, group_id: int, body: GroupRequest) -> GroupOut:
    """409 when another group already answers to the name: two groups of one name is the duplicate this
    contract refuses. Merging them is deleting one with `move_events_to` the other."""
    async with deps.connection(request.app.state.pool) as conn:
        try:
            renamed = await store.rename_group(conn, group_id, body.name)
        except store.GroupNameTaken as err:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=f"{err} — delete this group moving its events there to merge the two",
            ) from err
        if renamed is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"no group {group_id}")
        found = await store.find_group(conn, renamed.name)
    return _out(found or renamed)


@router.delete(
    "/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": Problem}, 422: {"model": Problem}},
)
async def delete_group(
    request: Request,
    group_id: int,
    move_events_to: int | None = Query(
        default=None, description="a group to move this one's events into first; absent, they come back ungrouped"
    ),
) -> None:
    """The events keep their observation and every sample — they come back ungrouped, or in `move_events_to`."""
    async with deps.connection(request.app.state.pool) as conn:
        try:
            deleted = await store.delete_group(conn, group_id, move_to=move_events_to)
        except store.NoSuchGroup as err:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail=f"no group {err.args[0]} to move the events into"
            ) from err
        except ValueError as err:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(err)) from err
        if not deleted:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"no group {group_id}")


@router.put(
    "/events/{event_id}/group",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": Problem}},
)
async def assign_group(request: Request, event_id: int, body: AssignRequest) -> None:
    async with deps.connection(request.app.state.pool) as conn:
        if not await store.assign_group(conn, event_id, body.group_id):
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail=f"no observed event with id {event_id}"
            )


def _out(group: Group) -> GroupOut:
    return GroupOut(id=group.id or 0, name=group.name, event_count=len(group.event_ids))
