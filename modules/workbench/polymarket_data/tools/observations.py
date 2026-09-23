"""track_event, the one tool that adds to the list of observations — reversible and exactly what the operator
clicks. No tool deletes collected history, changes configuration or touches money; grouping is `groups.py`."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from .. import group_names, provider, store, tracking, views
from ._shared import CHANGES_OBSERVATIONS, ToolContext
from .groups import lookalike_refusal


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


def register(mcp: FastMCP, ctx: ToolContext) -> None:
    @mcp.tool(annotations=CHANGES_OBSERVATIONS)
    async def track_event(reference: str, group: str | None = None) -> Tracked | dict:
        """Start collecting an event's prices. Accepts its polymarket.com address or its id
        from search_events / browse_events.

        From this moment the module samples every outcome of the event and fills in its
        recent past, so history is available within minutes rather than at once. Optionally
        files it under a group: an existing one in any spelling, a new one only when no group
        reads like it (list_groups shows them).

        Nothing is deleted by this and nothing can be: an event already observed is answered
        as such, and stopping later keeps everything collected.
        """
        group = group_names.clean(group) if group else None
        if group:
            # Asked before the provider is: a refusal here costs nothing and the model asks again.
            async with ctx.pool.acquire() as conn:
                if refusal := await lookalike_refusal(conn, group):
                    return refusal
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
            try:
                # One transaction, so a refusal at the ceiling leaves no empty group behind.
                async with conn.transaction():
                    group_id = (await store.create_group(conn, group))[0].id if group else None
                    event_id, already = await tracking.track(
                        conn,
                        event,
                        max_tracked_events=ctx.settings.max_tracked_events,
                        group_id=group_id,
                    )
            except tracking.LimitReached as err:
                # The refusal a model has to be able to act on. It says what to do first, because
                # "add whatever looks interesting" is exactly the request that reaches this ceiling.
                return {
                    "refused": str(err),
                    "do_first": (
                        "ask the operator to remove an observation in the terminal, then "
                        "try again; list_tracked_events shows what is being collected. "
                        "Removing one is not something this tool set can do — it takes the "
                        "collected history with it"
                    ),
                }
            [out] = await views.tracked_events(
                conn,
                interval_seconds=ctx.settings.sample_interval_seconds,
                provider_event_id=event.provider_event_id,
            )

        # The note below promises "the recent past is being filled in", and until this line
        # existed nothing kept that promise: the backfill had no caller outside its tests.
        if not already:
            ctx.ingest.event_tracked(event_id)

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
