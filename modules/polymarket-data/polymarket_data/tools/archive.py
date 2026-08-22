"""Reading what this module has collected.

Four tools, reduced for a model rather than for a chart. A chart wants every point; a model
wants the current state and the shape of the move, and asking it to read three thousand
points to find out that a probability rose four points is a bill for nothing.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from .. import changes as changes_module
from .. import store, views
from ._shared import PROBABILITY, READ_ONLY, Age, ToolContext

# The most points one history call returns. Beyond this a model is reading noise it pays for
# by the token; a longer view is what get_price_changes answers.
MAX_POINTS = 200


class OutcomeState(BaseModel):
    outcome_id: int = Field(description="pass this to get_price_history")
    name: str
    price: float | None = Field(default=None, description=PROBABILITY)
    price_age: Age | None = Field(
        default=None, description="when that price was observed, and how long ago"
    )


class MarketState(BaseModel):
    question: str
    label: str | None = None
    resolved_outcome: str | None = None
    mutually_exclusive: bool = Field(
        default=False,
        description="this market belongs to a set where exactly one wins; the Yes prices "
        "across that set need not sum to 1 and must not be reported as if they did",
    )
    outcomes: list[OutcomeState]


class TrackedEventSummary(BaseModel):
    event_id: str
    slug: str
    title: str
    group: str | None = None
    collection: str = Field(
        description="collecting, stalled, resolved or ended — being observed is not the "
        "same as prices arriving, and a stalled observation looks like a quiet market"
    )
    collection_note: str | None = None
    market_count: int


class EventDetail(TrackedEventSummary):
    markets: list[MarketState]


class HistoryPoint(BaseModel):
    at: datetime
    price: float = Field(description=PROBABILITY)


class HistoryOut(BaseModel):
    outcome_id: int
    points: list[HistoryPoint]
    truncated: bool = Field(
        description="true when the window held more points than were returned; the ones "
        "returned are evenly spread across it, not the first N"
    )
    collected_from: datetime | None = Field(
        default=None,
        description="the earliest moment this outcome was actually collected for. A gap "
        "after this moment means nobody traded; a gap before it means nobody was looking",
    )


def register(mcp: FastMCP, ctx: ToolContext) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def list_tracked_events(group: str | None = None) -> list[TrackedEventSummary]:
        """What this module is collecting, and whether collection is actually running."""
        async with ctx.pool.acquire() as conn:
            group_id = None
            if group:
                match = [g for g in await store.list_groups(conn) if g.name == group]
                if not match:
                    return []
                group_id = match[0].id
            events = await views.tracked_events(
                conn,
                interval_seconds=ctx.settings.sample_interval_seconds,
                group_id=group_id,
            )
        return [
            TrackedEventSummary(
                event_id=event.provider_event_id,
                slug=event.slug,
                title=event.title,
                group=event.group,
                collection=event.collection.state,
                collection_note=event.collection.reason,
                market_count=len(event.markets),
            )
            for event in events
        ]

    @mcp.tool(annotations=READ_ONLY)
    async def get_event(event_id: str) -> EventDetail | dict:
        """One tracked event in full: every market, every outcome, and the latest price of
        each with its age. A price without its age is a number nobody can date.
        """
        async with ctx.pool.acquire() as conn:
            events = await views.tracked_events(
                conn,
                interval_seconds=ctx.settings.sample_interval_seconds,
                provider_event_id=event_id,
            )
        if not events:
            return {
                "refused": f"{event_id} is not an event this module observes",
                "do_first": "list_tracked_events shows what is observed; track_event adds one",
            }
        event = events[0]
        return EventDetail(
            event_id=event.provider_event_id,
            slug=event.slug,
            title=event.title,
            group=event.group,
            collection=event.collection.state,
            collection_note=event.collection.reason,
            market_count=len(event.markets),
            markets=[
                MarketState(
                    question=market.question,
                    label=market.label,
                    resolved_outcome=market.resolved_outcome,
                    mutually_exclusive=market.neg_risk,
                    outcomes=[
                        OutcomeState(
                            outcome_id=outcome.id,
                            name=outcome.name,
                            price=outcome.price,
                            price_age=Age.of(outcome.price_at),
                        )
                        for outcome in market.outcomes
                    ],
                )
                for market in event.markets
            ],
        )

    @mcp.tool(annotations=READ_ONLY)
    async def get_price_history(outcome_id: int, hours: int = 24) -> HistoryOut | dict:
        """One outcome's probability over the last `hours`, from this module's own archive.

        Thinned to at most 200 evenly spread points: a day of minute samples is 1440, and a
        model reading all of them pays for noise. Use get_price_changes for the shape of the
        move rather than the points.
        """
        until = datetime.now(UTC)
        since = until - timedelta(hours=max(1, hours))
        async with ctx.pool.acquire() as conn:
            exists = await conn.fetchval("SELECT 1 FROM outcomes WHERE id = $1", outcome_id)
            if not exists:
                return {
                    "refused": f"there is no outcome with id {outcome_id}",
                    "do_first": "get_event lists the outcome ids of a tracked event",
                }
            series = await store.history(conn, outcome_id, since=since, until=until)
            collected = await store.collected_ranges(conn, outcome_id)

        priced = [
            HistoryPoint(at=sample.observed_at, price=float(sample.midpoint))
            for sample in series
            if sample.midpoint is not None
        ]
        truncated = len(priced) > MAX_POINTS
        if truncated:
            # Evenly spread rather than the first N: the first 200 of a day would be the
            # first three hours, and a model would read a whole day's shape off them.
            step = len(priced) / MAX_POINTS
            priced = [priced[int(index * step)] for index in range(MAX_POINTS)]

        return HistoryOut(
            outcome_id=outcome_id,
            points=priced,
            truncated=truncated,
            collected_from=collected[0].starts_at if collected else None,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def get_price_changes(event_id: str) -> dict:
        """How each outcome of a tracked event has moved over 5m, 1h, 4h, 24h and 7d.

        A window the collected history does not reach comes back as null with the reason,
        never as zero — zero would be a claim about the market rather than about the archive.
        Changes are in points of the 0..1 scale: 0,04 is four percentage points.
        """
        async with ctx.pool.acquire() as conn:
            events = await store.load_events(conn, provider_event_id=event_id)
            if not events:
                return {
                    "refused": f"{event_id} is not an event this module observes",
                    "do_first": "track_event starts collecting it; history begins then",
                }
            event = events[0]
            answer = []
            for market in event.markets:
                for outcome in market.outcomes:
                    computed = await changes_module.changes_for_outcome(
                        conn, outcome.id or 0, outcome.name
                    )
                    answer.append(
                        {
                            "outcome_id": computed.outcome_id,
                            "market": market.group_item_title or market.question,
                            "outcome": computed.name,
                            "price": computed.price,
                            "changes": {
                                window.window: window.change for window in computed.windows
                            },
                            "unavailable": {
                                window.window: window.unavailable
                                for window in computed.windows
                                if window.unavailable
                            },
                        }
                    )
        return {"event_id": event_id, "slug": event.slug, "outcomes": answer}
