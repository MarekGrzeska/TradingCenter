"""What topics found, and what the operator does with it. The agent has no door here: a topic proposes, and following a
channel, naming a film for analysis and turning a channel away are decisions for the person looking at the list."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response, status

from .. import candidates, store
from ..contract import (
    CandidateChannelOut,
    CandidateChoice,
    CandidateOut,
    CandidatesOut,
    ChannelOut,
    IgnoredChannelOut,
    IgnoredChannelsOut,
    Problem,
    QueuedOut,
)
from ..watchlist import WatchlistRefused
from .deps import connection

router = APIRouter(tags=["candidates"])

MAX_LIMIT = 200
_PROBLEMS: dict[int | str, dict[str, Any]] = {404: {"model": Problem}, 422: {"model": Problem}}


def _refuse(detail: str) -> HTTPException:
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_CONTENT, detail=Problem(detail=detail, cause="request").model_dump()
    )


def _missing(what: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, detail=Problem(detail=what).model_dump())


@router.get("/candidates", response_model=CandidatesOut, responses={422: {"model": Problem}})
async def list_candidates(
    request: Request,
    view: str = Query(default="open"),
    sort: str = Query(default="found"),
    topic_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=MAX_LIMIT),
) -> CandidatesOut:
    """Films a topic's search found, newest first in the order asked for. Reading it asks nobody anything."""
    if view not in store.CANDIDATE_VIEWS:
        raise _refuse(f"view must be one of {', '.join(store.CANDIDATE_VIEWS)}; got {view!r}")
    if sort not in store.CANDIDATE_SORTS:
        raise _refuse(f"sort must be one of {', '.join(store.CANDIDATE_SORTS)}; got {sort!r}")
    async with connection(request.app.state.pool) as conn:
        found = await store.list_candidates(conn, view=view, sort=sort, topic_id=topic_id, limit=limit)
    return CandidatesOut(
        candidates=[CandidateOut.of(candidate) for candidate in found],
        view=view,  # type: ignore[arg-type]
        sort=sort,  # type: ignore[arg-type]
    )


@router.post("/candidates/{video_id}/follow-channel", response_model=CandidateChannelOut, responses=_PROBLEMS)
async def follow_channel(request: Request, video_id: str, body: CandidateChoice) -> CandidateChannelOut:
    """Follow the candidate's channel. The channel's other open candidates are settled with it."""
    state = request.app.state
    try:
        followed = await candidates.follow_channel_of(
            state.pool, state.providers, state.settings, video_id, prompt=body.prompt_id
        )
    except candidates.CandidateMissing as err:
        raise _missing(f"no candidate {video_id!r}") from err
    except WatchlistRefused as err:
        raise _refuse(str(err)) from err
    return CandidateChannelOut(channel=ChannelOut.of(followed.channel), created=followed.created)


@router.post("/candidates/{video_id}/analyse", response_model=QueuedOut, responses=_PROBLEMS)
async def analyse(request: Request, video_id: str, body: CandidateChoice) -> QueuedOut:
    """Have the candidate's film transcribed and read now, as if its address had been pasted."""
    state = request.app.state
    try:
        queued = await candidates.analyse_candidate(
            state.pool, state.providers, state.settings, video_id, prompt=body.prompt_id
        )
    except candidates.CandidateMissing as err:
        raise _missing(f"no candidate {video_id!r}") from err
    except WatchlistRefused as err:
        raise _refuse(str(err)) from err
    if queued.process and getattr(state, "ingest", None) is not None:
        state.ingest.start_now(queued.video_id)
    return QueuedOut(video_id=queued.video_id, title=queued.title, created=queued.created)


@router.post("/candidates/{video_id}/dismiss", response_model=CandidateOut, responses=_PROBLEMS)
async def dismiss(request: Request, video_id: str) -> CandidateOut:
    """Take the film off the list for good: the same film is not offered again."""
    state = request.app.state
    try:
        decided = await candidates.dismiss(state.pool, state.providers.clock, video_id)
    except candidates.CandidateMissing as err:
        raise _missing(f"no candidate {video_id!r}") from err
    except WatchlistRefused as err:
        raise _refuse(str(err)) from err
    return CandidateOut.of(decided)


@router.post("/candidates/{video_id}/ignore-channel", response_model=CandidateOut, responses=_PROBLEMS)
async def ignore_channel(request: Request, video_id: str) -> CandidateOut:
    """Stop offering the candidate's channel: its open candidates leave the list and its next films do not join it."""
    state = request.app.state
    try:
        decided = await candidates.ignore_channel_of(state.pool, state.providers.clock, video_id)
    except candidates.CandidateMissing as err:
        raise _missing(f"no candidate {video_id!r}") from err
    except WatchlistRefused as err:
        raise _refuse(str(err)) from err
    return CandidateOut.of(decided)


@router.get("/ignored-channels", response_model=IgnoredChannelsOut)
async def ignored_channels(request: Request) -> IgnoredChannelsOut:
    async with connection(request.app.state.pool) as conn:
        found = await store.list_ignored_channels(conn)
    return IgnoredChannelsOut(channels=[IgnoredChannelOut.of(channel) for channel in found])


@router.delete(
    "/ignored-channels/{channel_id}", status_code=status.HTTP_204_NO_CONTENT, responses={404: {"model": Problem}}
)
async def unignore_channel(request: Request, channel_id: str) -> Response:
    """Offer the channel's next films again. What was already decided about stays decided."""
    async with connection(request.app.state.pool) as conn:
        removed = await store.unignore_channel(conn, channel_id)
    if not removed:
        raise _missing(f"channel {channel_id!r} is not ignored")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
