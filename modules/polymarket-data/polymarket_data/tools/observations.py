"""The three tools that change something, and the boundary around them.

This is the deliberate departure from `market-data-tools`, which holds outright that its set
only reads and that no setting may add a writing tool to it. That rule is right there and
wrong here, and the difference is what "writing" means in each module. There, a write would
mutate the candle archive: data nobody can reconstruct, in a module where a quiet change is
corruption. Here, a write is the **list of observations** — exactly what the operator clicks
in the terminal, entirely reversible, with no effect beyond this module starting or stopping
asking the provider about an event.

The boundary is somewhere else and is just as hard: **no tool deletes collected history**,
none changes the module's configuration, and none touches anything to do with money — this
system trades nothing on Polymarket. Deleting is a route on the REST contract, because it is
the one act here that cannot be undone.

`tests/test_tools_surface.py` holds this: a tool reaching past the observation list fails
before it is deployed, rather than being noticed at review.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from .. import provider, store, tracking, views
from ._shared import CHANGES_OBSERVATIONS, ToolContext


class Tracked(BaseModel):
    event_id: str
    slug: str
    title: str
    group: str | None = None
    market_count: int
    already_tracked: bool = Field(
        description="true when this event was already observed — no second observation was "
        "created and no collected history was disturbed"
    )
    note: str = Field(
        description="what happens next, so the answer does not read as if data already exists"
    )


class Untracked(BaseModel):
    event_id: str
    stopped: bool
    note: str


class GroupCreated(BaseModel):
    group: str
    note: str


def register(mcp: FastMCP, ctx: ToolContext) -> None:
    @mcp.tool(annotations=CHANGES_OBSERVATIONS)
    async def track_event(reference: str, group: str | None = None) -> Tracked | dict:
        """Start collecting an event's prices. Accepts its polymarket.com address or its id
        from search_events / browse_events.

        From this moment the module samples every outcome of the event and fills in its
        recent past, so history is available within minutes rather than at once. Optionally
        files it under an observation group.

        Nothing is deleted by this and nothing can be: an event already observed is answered
        as such, and stopping later keeps everything collected.
        """
        try:
            event = await ctx.provider.event_by_reference(reference)
        except provider.ProviderHasNothing:
            return {
                "refused": f"Polymarket has no event at {reference!r}",
                "do_first": "search_events or browse_events will give a valid id or address",
            }
        except provider.ProviderError as err:
            return {"refused": f"the provider could not be read: {err}", "retryable": True}

        async with ctx.pool.acquire() as conn:
            group_id = (await store.create_group(conn, group)).id if group else None
            try:
                _, already = await tracking.track(
                    conn,
                    event,
                    max_tracked_events=ctx.settings.max_tracked_events,
                    group_id=group_id,
                )
            except tracking.LimitReached as err:
                # The refusal a model has to be able to act on. It says what to do first,
                # because "add whatever looks interesting" is exactly the request that
                # reaches this ceiling.
                return {
                    "refused": str(err),
                    "do_first": (
                        "untrack_event on something no longer interesting, then try again; "
                        "list_tracked_events shows what is being collected"
                    ),
                }
            [out] = await views.tracked_events(
                conn,
                interval_seconds=ctx.settings.sample_interval_seconds,
                provider_event_id=event.provider_event_id,
            )

        return Tracked(
            event_id=out.provider_event_id,
            slug=out.slug,
            title=out.title,
            group=out.group,
            market_count=len(out.markets),
            already_tracked=already,
            note=(
                "already being collected; its history is available now"
                if already
                else "collection has started; the recent past is being filled in, so "
                "get_price_changes will answer more windows over the next few minutes"
            ),
        )

    @mcp.tool(annotations=CHANGES_OBSERVATIONS)
    async def untrack_event(event_id: str) -> Untracked | dict:
        """Stop collecting an event's prices.

        Everything already collected stays and stays readable — this stops the sampling, it
        does not delete anything. Deleting collected history is not something any tool here
        can do; it is an operator's action in the terminal.
        """
        async with ctx.pool.acquire() as conn:
            stopped = await tracking.untrack(conn, event_id)
        if not stopped:
            return {
                "refused": f"{event_id} is not currently being collected",
                "do_first": "list_tracked_events shows what is",
            }
        return Untracked(
            event_id=event_id,
            stopped=True,
            note="sampling stopped; every price already collected is still readable",
        )

    @mcp.tool(annotations=CHANGES_OBSERVATIONS)
    async def create_group(name: str) -> GroupCreated | dict:
        """Create an observation group — a local category for sorting what is collected.

        Not one of Polymarket's tags: those describe the public database and are what
        browse_events filters on. Asking twice for the same group is not an error.
        """
        cleaned = name.strip()
        if not cleaned:
            return {"refused": "a group needs a name", "do_first": "pass a non-empty name"}
        async with ctx.pool.acquire() as conn:
            group = await store.create_group(conn, cleaned)
        return GroupCreated(
            group=group.name,
            note="pass this name as `group` to track_event to file events under it",
        )
