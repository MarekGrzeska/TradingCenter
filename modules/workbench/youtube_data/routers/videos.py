"""Reading the archive, and putting one film in it by hand. Nothing here discovers, transcribes or reads: those are the
loop's, and a route that did them as a side effect of being read would make the archive depend on who looked."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request, status

from .. import store, views, watchlist
from ..contract import (
    AnalyseIn,
    Problem,
    QueuedOut,
    StateOut,
    TranscriptPageOut,
    VideoOut,
    VideosOut,
)
from ..models import STATES
from ..watchlist import WatchlistRefused
from .deps import connection

router = APIRouter(tags=["videos"])

MAX_LIMIT = 200
MAX_PAGE_CHARS = 20_000


def _refuse(detail: str) -> HTTPException:
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_CONTENT, detail=Problem(detail=detail, cause="request").model_dump()
    )


@router.get("/videos", response_model=VideosOut, responses={422: {"model": Problem}})
async def videos(
    request: Request,
    hours: int | None = Query(default=None, ge=1, le=24 * 30),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    channel_id: str | None = Query(default=None),
    topic_id: int | None = Query(default=None),
    instrument: str | None = Query(default=None, description="a name or ticker a reading mentions"),
    min_score: int | None = Query(default=None, ge=1, le=10),
    state: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=MAX_LIMIT),
) -> VideosOut:
    """A window of films, newest first, each with its reading if it has one and never with its transcript."""
    if state is not None and state not in STATES:
        raise _refuse(f"state must be one of {', '.join(STATES)}; got {state!r}")
    # The archive's own now: in a simulation the clock runs faster than the wall, and a window measured against the
    # wall would ask for films that are, as far as the archive is concerned, in the future or the far past.
    start, end = views.window(hours=hours, since=since, until=until, now=request.app.state.providers.clock.now())
    if start >= end:
        raise _refuse(f"the window ends before it starts: {start.isoformat()} to {end.isoformat()}")

    async with connection(request.app.state.pool) as conn:
        return await views.videos(
            conn,
            start=start,
            end=end,
            channel_id=channel_id,
            topic_id=topic_id,
            instrument=instrument,
            min_score=min_score,
            state=state,
            limit=limit,
        )


@router.get("/videos/{video_id}", response_model=VideoOut, responses={404: {"model": Problem}})
async def video(request: Request, video_id: str) -> VideoOut:
    async with connection(request.app.state.pool) as conn:
        found = await store.get_film(conn, video_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=Problem(detail=f"no film {video_id!r}").model_dump())
    return VideoOut.of(found)


@router.get(
    "/videos/{video_id}/transcript", response_model=TranscriptPageOut, responses={404: {"model": Problem}}
)
async def transcript(
    request: Request,
    video_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=4000, ge=1, le=MAX_PAGE_CHARS),
) -> TranscriptPageOut:
    """A page of the words. Kept apart from the film so a list never carries tens of kilobytes it did not ask for."""
    async with connection(request.app.state.pool) as conn:
        page = await store.transcript_page(conn, video_id, offset=offset, limit=limit)
    if page is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=Problem(detail=f"no transcript for {video_id!r} — none was fetched, or it has none").model_dump(),
        )
    end = offset + len(page.text)
    return TranscriptPageOut(
        video_id=video_id,
        language=page.language,
        provider=page.provider,
        automatic=page.automatic,
        model=page.model,
        simulated=page.simulated,
        offset=offset,
        total_chars=page.total_chars,
        text=page.text,
        next_offset=end if end < page.total_chars else None,
    )


@router.post("/videos", response_model=QueuedOut, responses={422: {"model": Problem}})
async def analyse(request: Request, body: AnalyseIn) -> QueuedOut:
    """Accept one film, named by address or id, and have it transcribed and read now, in the background — not on the
    loop's next pass. Costs what asking the source about it costs; the answer does not wait for the reading."""
    state = request.app.state
    try:
        queued = await watchlist.analyse_film(state.pool, state.providers, state.settings, body.reference)
    except WatchlistRefused as err:
        raise _refuse(str(err)) from err
    if queued.process and getattr(state, "ingest", None) is not None:
        state.ingest.start_now(queued.video_id)
    return QueuedOut(video_id=queued.video_id, title=queued.title, created=queued.created)


@router.get("/state", response_model=StateOut, tags=["meta"])
async def state(request: Request) -> StateOut:
    """What the archive is doing: which providers answer, what the day has cost, how old the loop's last pass is.

    Read before a screen says "no films", because a quiet channel, a blocked provider and a stopped loop produce the same
    empty window."""
    app_state = request.app.state
    heartbeats = getattr(app_state, "heartbeats", None)
    async with connection(app_state.pool) as conn:
        return await views.state(
            conn,
            app_state.settings,
            app_state.providers,
            heartbeat=None if heartbeats is None else heartbeats["ingest"],
            alerts_configured=getattr(app_state, "alerts", None) is not None,
        )
