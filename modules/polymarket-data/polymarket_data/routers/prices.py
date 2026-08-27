"""Reading what has been collected: the snapshot, one outcome's series, and the windows."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, Request, status

from .. import changes, store, views
from ..contract import ChangesOut, HistoryOut, PricePoint, Problem, SnapshotOut

router = APIRouter(tags=["prices"])

# What a history read covers when the caller names no range. A week, because that is the longest change
# window this module publishes, so the default answer draws everything the windows describe.
DEFAULT_HISTORY_SPAN = timedelta(days=7)


@router.get("/snapshot", response_model=SnapshotOut)
async def snapshot(request: Request) -> SnapshotOut:
    """Every tracked outcome's newest price, in one read.

    One request rather than one per event: the screen this fills has a row per outcome, and a
    single measured event holds 128 markets.
    """
    async with request.app.state.pool.acquire() as conn:
        return await views.snapshot(conn)


@router.get(
    "/outcomes/{outcome_id}/history",
    response_model=HistoryOut,
    responses={404: {"model": Problem}},
)
async def history(
    request: Request,
    outcome_id: int,
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
) -> HistoryOut:
    """One outcome's series, oldest first, with the range it was actually collected for.

    The second half is not decoration: a gap inside a collected range means nobody traded,
    and the same gap outside one means this module was not looking. Without the range the
    two are the same absence.
    """
    end = until or datetime.now(UTC)
    start = since or end - DEFAULT_HISTORY_SPAN

    async with request.app.state.pool.acquire() as conn:
        exists = await conn.fetchval("SELECT 1 FROM outcomes WHERE id = $1", outcome_id)
        if not exists:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, detail=f"no outcome with id {outcome_id}"
            )
        series = await store.history(conn, outcome_id, since=start, until=end)
        collected = await store.collected_ranges(conn, outcome_id)

    return HistoryOut(
        outcome_id=outcome_id,
        points=[
            PricePoint(
                at=sample.observed_at,
                price=float(sample.midpoint) if sample.midpoint is not None else None,
                last_trade=float(sample.last_trade) if sample.last_trade is not None else None,
            )
            for sample in series
        ],
        collected_from=collected[0].starts_at if collected else None,
        collected_to=collected[-1].ends_at if collected else None,
    )


@router.get(
    "/events/{provider_event_id}/changes",
    response_model=ChangesOut,
    responses={404: {"model": Problem}},
)
async def event_changes(request: Request, provider_event_id: str) -> ChangesOut:
    """The seven windows, computed here rather than kept in a table.

    There is no second worker maintaining them and no table to drift from the history: at
    this scale the windows are one query each over data the archive already holds. A window
    the collected history does not reach is a null with its reason, never a zero — a zero
    would be a claim about the market rather than about the archive.
    """
    async with request.app.state.pool.acquire() as conn:
        events = await store.load_events(conn, provider_event_id=provider_event_id)
        if not events:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail=f"{provider_event_id} is not an event this module observes",
            )
        event = events[0]
        outcomes = [
            (outcome.id or 0, f"{market.group_item_title or market.question} — {outcome.name}")
            for market in event.markets
            for outcome in market.outcomes
        ]
        computed = [
            await changes.changes_for_outcome(conn, outcome_id, name)
            for outcome_id, name in outcomes
        ]
    return ChangesOut(event_id=event.id or 0, outcomes=computed)
