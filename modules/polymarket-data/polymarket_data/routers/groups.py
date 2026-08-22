"""Observation groups — this module's own categories.

Not the provider's tags. A tag describes the public database and is what browsing filters on;
a group describes what we watch, and the two are kept apart on purpose because an operator
sorting their own screen is a different act from searching somebody else's index.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from .. import store
from ..contract import GroupOut, Problem

router = APIRouter(tags=["groups"])


class GroupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class AssignRequest(BaseModel):
    group_id: int | None = Field(
        default=None, description="null takes the event out of every group without untracking it"
    )


@router.get("/groups", response_model=list[GroupOut])
async def list_groups(request: Request) -> list[GroupOut]:
    async with request.app.state.pool.acquire() as conn:
        groups = await store.list_groups(conn)
    return [
        GroupOut(id=group.id or 0, name=group.name, event_count=len(group.event_ids))
        for group in groups
    ]


@router.post("/groups", response_model=GroupOut, status_code=status.HTTP_201_CREATED)
async def create_group(request: Request, body: GroupRequest) -> GroupOut:
    """Idempotent on the name: asking twice for the same category is not an error."""
    async with request.app.state.pool.acquire() as conn:
        group = await store.create_group(conn, body.name.strip())
        groups = {existing.id: existing for existing in await store.list_groups(conn)}
    found = groups.get(group.id)
    return GroupOut(
        id=group.id or 0,
        name=group.name,
        event_count=len(found.event_ids) if found else 0,
    )


@router.delete(
    "/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": Problem}},
)
async def delete_group(request: Request, group_id: int) -> None:
    """The events keep their observation and every sample — they come back ungrouped."""
    async with request.app.state.pool.acquire() as conn:
        if not await store.delete_group(conn, group_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"no group {group_id}")


@router.put(
    "/events/{event_id}/group",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": Problem}},
)
async def assign_group(request: Request, event_id: int, body: AssignRequest) -> None:
    async with request.app.state.pool.acquire() as conn:
        if not await store.assign_group(conn, event_id, body.group_id):
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail=f"no observed event with id {event_id}"
            )
