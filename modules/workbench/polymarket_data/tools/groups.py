"""The five tools over observation groups. A group holds no data, so a model may rename, merge and delete them — but
it asks before making one that reads like another: left alone, models made "Crypto", "crypto" and "Cryptocurrency"."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from .. import group_names, store
from ._shared import CHANGES_OBSERVATIONS, READ_ONLY, REMOVES_A_GROUP, ToolContext


class GroupSummary(BaseModel):
    name: str
    event_count: int


class GroupCreated(BaseModel):
    group: str
    already_existed: bool = Field(
        description="true when a group of this name, in any case or spacing, was already there "
        "and is the one answered — nothing new was made"
    )
    note: str


class GroupChanged(BaseModel):
    group: str | None = Field(default=None, description="the group's name now; null when it is gone")
    note: str


async def _no_group(conn, name: str) -> dict:
    existing = await store.list_groups(conn)
    return {
        "refused": f"there is no group named {name!r}",
        "do_first": "use one of these names, or create_group first: "
        + (", ".join(repr(group.name) for group in existing) or "(no groups yet)"),
    }


async def lookalike_refusal(conn, name: str) -> dict | None:
    """The refusal for a name that is no group's but reads like one; `None` when the name is free or already a
    group's. Shared by track_event, so filing under a new group and creating one ask the same question."""
    if await store.find_group(conn, name) is not None:
        return None
    lookalikes = group_names.similar(name, [group.name for group in await store.list_groups(conn)])
    if not lookalikes:
        return None
    return {
        "refused": f"{name!r} reads like a group that already exists, so nothing was created",
        "similar_groups": lookalikes,
        "do_first": "use one of similar_groups; only if the operator means a different category, "
        "call create_group with confirm_new=true",
    }


def register(mcp: FastMCP, ctx: ToolContext) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def list_groups() -> list[GroupSummary]:
        """Every observation group and how many observed events are filed under it. Read this
        before creating or naming a group — reusing one beats a second spelling of it."""
        async with ctx.pool.acquire() as conn:
            groups = await store.list_groups(conn)
        return [GroupSummary(name=group.name, event_count=len(group.event_ids)) for group in groups]

    @mcp.tool(annotations=CHANGES_OBSERVATIONS)
    async def create_group(name: str, confirm_new: bool = False) -> GroupCreated | dict:
        """Create an observation group — a local category for sorting what is collected, not one
        of Polymarket's tags. A name matching an existing group in any case or spacing answers
        that group. A name that merely reads like one ("tariff" beside "Tariffs") is refused with
        the lookalikes, unless confirm_new is true because the operator means a new category.
        """
        cleaned = group_names.clean(name)
        if not cleaned:
            return {"refused": "a group needs a name", "do_first": "pass a non-empty name"}
        async with ctx.pool.acquire() as conn:
            if not confirm_new and (refusal := await lookalike_refusal(conn, cleaned)):
                return refusal
            group, created = await store.create_group(conn, cleaned)
        return GroupCreated(
            group=group.name,
            already_existed=not created,
            note="pass this name as `group` to track_event or move_event_to_group",
        )

    @mcp.tool(annotations=CHANGES_OBSERVATIONS)
    async def rename_group(group: str, new_name: str) -> GroupChanged | dict:
        """Rename an observation group; its events stay in it. Refused when another group already
        has the new name — merging two groups is delete_group with move_events_to.
        """
        cleaned = group_names.clean(new_name)
        if not cleaned:
            return {"refused": "a group needs a name", "do_first": "pass a non-empty new_name"}
        async with ctx.pool.acquire() as conn:
            found = await store.find_group(conn, group)
            if found is None or found.id is None:
                return await _no_group(conn, group)
            try:
                renamed = await store.rename_group(conn, found.id, cleaned)
            except store.GroupNameTaken as err:
                return {
                    "refused": f"a group named {err.existing.name!r} already exists",
                    "do_first": f"to merge, delete_group {found.name!r} with "
                    f"move_events_to={err.existing.name!r}",
                }
            if renamed is None:
                return await _no_group(conn, group)
        return GroupChanged(
            group=renamed.name, note=f"{len(found.event_ids)} event(s) moved with it"
        )

    @mcp.tool(annotations=CHANGES_OBSERVATIONS)
    async def move_event_to_group(event_id: str, group: str | None = None) -> GroupChanged | dict:
        """File an observed event under an existing group, or take it out of every group with
        group=null. The observation and its history are untouched either way.
        """
        async with ctx.pool.acquire() as conn:
            event = await store.tracked_event_ref(conn, event_id)
            if event is None:
                return {
                    "refused": f"{event_id} is not an event this module observes",
                    "do_first": "list_tracked_events shows what is observed",
                }
            target = None
            if group is not None:
                target = await store.find_group(conn, group)
                if target is None:
                    return await _no_group(conn, group)
            if not await store.assign_group(conn, event["id"], target.id if target else None):
                return {"refused": f"{event_id} stopped being observed just now"}
        return GroupChanged(
            group=target.name if target else None,
            note=f"{event['title']} is now "
            + (f"in {target.name!r}" if target else "in no group"),
        )

    @mcp.tool(annotations=REMOVES_A_GROUP)
    async def delete_group(group: str, move_events_to: str | None = None) -> GroupChanged | dict:
        """Delete an observation group. Its events stay observed with all their history — they
        come back ungrouped, or land in move_events_to first, which is how two duplicate groups
        become one.
        """
        async with ctx.pool.acquire() as conn:
            found = await store.find_group(conn, group)
            if found is None or found.id is None:
                return await _no_group(conn, group)
            target = None
            if move_events_to is not None:
                target = await store.find_group(conn, move_events_to)
                if target is None or target.id is None:
                    return await _no_group(conn, move_events_to)
                if target.id == found.id:
                    return {
                        "refused": "a group cannot take in its own events on the way out",
                        "do_first": "name a different group in move_events_to, or leave it out",
                    }
            try:
                deleted = await store.delete_group(
                    conn, found.id, move_to=target.id if target else None
                )
            except store.NoSuchGroup:
                return await _no_group(conn, move_events_to or "")
            if not deleted:
                return await _no_group(conn, group)
        return GroupChanged(
            group=None,
            note=f"{found.name!r} is gone; its {len(found.event_ids)} event(s) are still observed "
            + (f"and now in {target.name!r}" if target else "and now in no group"),
        )
