"""What is under observation, and the two acts that change it.

Three acts, in fact, and the third is the one worth naming: **deleting collected history
lives here and only here**. Ending an observation stops the sampling and keeps every sample;
deleting is separate, irreversible, and out of reach of every tool.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, status

from .. import provider, store, tracking, views
from ..contract import DeletionResult, Problem, TrackedEventOut, TrackRequest, TrackResult

log = logging.getLogger(__name__)

router = APIRouter(tags=["observations"])


def _settings(request: Request):
    return request.app.state.settings


@router.get("/events", response_model=list[TrackedEventOut])
async def list_events(
    request: Request, group_id: int | None = None
) -> list[TrackedEventOut]:
    """Every observation. There is no filter for stopped ones, because there are none:
    an observation is collected or it is gone."""
    async with request.app.state.pool.acquire() as conn:
        return await views.tracked_events(
            conn,
            interval_seconds=_settings(request).sample_interval_seconds,
            group_id=group_id,
        )


@router.get(
    "/events/{provider_event_id}",
    response_model=TrackedEventOut,
    responses={404: {"model": Problem}},
)
async def read_event(request: Request, provider_event_id: str) -> TrackedEventOut:
    async with request.app.state.pool.acquire() as conn:
        found = await views.tracked_events(
            conn,
            interval_seconds=_settings(request).sample_interval_seconds,
            provider_event_id=provider_event_id,
        )
    if not found:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"{provider_event_id} is not an event this module observes",
        )
    return found[0]


@router.post(
    "/events",
    response_model=TrackResult,
    responses={404: {"model": Problem}, 409: {"model": Problem}, 502: {"model": Problem}},
)
async def track_event(request: Request, body: TrackRequest) -> TrackResult:
    """Brings an event under observation, atomically or not at all.

    An event already observed is not an error and does not create a second observation — the
    answer says so, which is what lets a caller ask without first remembering whether it
    asked before.
    """
    settings = _settings(request)
    client: provider.PolymarketClient = request.app.state.provider

    try:
        event = await client.event_by_reference(body.reference)
    except provider.ProviderHasNothing as err:
        # An answer to the question, not a failure of this module.
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"the provider has no event at {body.reference!r}",
        ) from err
    except provider.ProviderUnusable as err:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail=f"the provider answered with something this module cannot read: {err}",
        ) from err
    except provider.ProviderRefused as err:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, detail=f"the provider refused: {err}"
        ) from err

    async with request.app.state.pool.acquire() as conn:
        group_id = None
        if body.group:
            group_id = (await store.create_group(conn, body.group)).id
        try:
            event_id, already = await tracking.track(
                conn,
                event,
                max_tracked_events=settings.max_tracked_events,
                group_id=group_id,
            )
        except tracking.LimitReached as err:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(err)) from err

        [out] = await views.tracked_events(
            conn,
            interval_seconds=settings.sample_interval_seconds,
            provider_event_id=event.provider_event_id,
        )

    # Outside the connection and after the row exists: the past is filled by its own task, so
    # this request does not wait on six provider calls per outcome. Only for a new
    # observation — re-tracking something already observed has nothing to reach back for.
    if not already:
        request.app.state.ingest.event_tracked(event_id)
    return TrackResult(event=out, already_tracked=already)


@router.delete(
    "/events/{provider_event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": Problem}},
)
async def remove_event(request: Request, provider_event_id: str) -> None:
    """The observation and everything collected for it, in one indivisible act.

    **The only way an event leaves the list**, and the second of the two acts in this module
    that cannot be undone. There is no stopping without removing: an observation that neither
    collects nor leaves is a row nobody can say the purpose of, and it used to be produced by
    a route that existed to produce it (`openspec/specs/polymarket-data-tracking`).

    A model cannot reach this. The tool surface writes to the observation list by adding to
    it, and adding is the whole of what it does.

    `204` rather than the removed event: what is returned about a thing that no longer exists
    is a shape somebody will be tempted to read.
    """
    async with request.app.state.pool.acquire() as conn:
        if not await store.remove_event(conn, provider_event_id):
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail=f"{provider_event_id} is not an event this module observes",
            )
    log.warning("observation removed with all of its history: %s", provider_event_id)


@router.delete(
    "/events/{provider_event_id}/history",
    response_model=DeletionResult,
    responses={404: {"model": Problem}},
)
async def delete_history(request: Request, provider_event_id: str) -> DeletionResult:
    """The one act in this module that cannot be undone, and the reason it is here.

    A model can start and stop an observation; it cannot reach this. Samples and the record
    of what was collected go together, in one transaction — a range surviving its samples is
    binding on planning, so the window would read as already collected and nothing would
    come back to it.
    """
    async with request.app.state.pool.acquire() as conn:
        events = await store.load_events(conn, provider_event_id=provider_event_id)
        if not events:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail=f"{provider_event_id} is not an event this module observes",
            )
        samples, ranges = await store.delete_history(conn, events[0].id or 0)
    log.warning(
        "history deleted for event %s: %d samples, %d collected ranges",
        provider_event_id,
        samples,
        ranges,
    )
    return DeletionResult(samples_deleted=samples, ranges_deleted=ranges)
