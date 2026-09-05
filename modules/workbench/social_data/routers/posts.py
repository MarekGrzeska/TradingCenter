"""Reading what has been collected. Every route here reads; there is no route that collects, and
that absence is the contract's own rule rather than an omission."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, Request, status

from .. import store, views
from ..contract import PostOut, PostsOut, Problem, StateOut

router = APIRouter(tags=["posts"])

MAX_LIMIT = 500


def _refuse(detail: str) -> HTTPException:
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=Problem(detail=detail, cause="request").model_dump(),
    )


@router.get("/posts", response_model=PostsOut, responses={422: {"model": Problem}})
async def posts(
    request: Request,
    hours: int | None = Query(default=None, ge=1, le=24 * 30),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    source: str | None = Query(default=None),
    min_score: int | None = Query(default=None, ge=1, le=10),
    topic: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=MAX_LIMIT),
) -> PostsOut:
    """A window of posts, newest first.

    `hours` is the short way of asking and an explicit range the exact one; both are here because
    the screens ask the first and a model asks the second.
    """
    settings = request.app.state.settings
    start, end = views.window(
        hours=hours, since=since, until=until, default_hours=settings.collect_window_hours
    )
    if start >= end:
        raise _refuse(f"the window ends before it starts: {start.isoformat()} to {end.isoformat()}")

    async with request.app.state.pool.acquire() as conn:
        return await views.posts(
            conn,
            start=start,
            end=end,
            source=source,
            min_score=min_score,
            topic=topic,
            limit=limit,
        )


@router.get(
    "/posts/{source}/{external_id}",
    response_model=PostOut,
    responses={404: {"model": Problem}},
)
async def post(request: Request, source: str, external_id: str) -> PostOut:
    """One post in full, by the pair that identifies it."""
    async with request.app.state.pool.acquire() as conn:
        found = await store.post_by_external_id(conn, source, external_id)
    if found is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=Problem(detail=f"no post {external_id!r} from {source!r}").model_dump(),
        )
    return PostOut.of(found)


@router.get("/state", response_model=StateOut, tags=["meta"])
async def state(request: Request) -> StateOut:
    """What the archive is doing: since when, how recently, and whether a model is configured.

    Read before a screen says "no posts", because a quiet source and one that has been unreachable
    for three hours produce the same empty window.
    """
    async with request.app.state.pool.acquire() as conn:
        return await views.state(conn, request.app.state.settings, now=datetime.now(UTC))
