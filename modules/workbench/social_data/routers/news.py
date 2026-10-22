"""The news: read a window or the kept ones, read how each feed is doing, and keep a headline or let it go.
`PUT /news/keep` is the one route in this contract that writes, and all it writes is that decision."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, Request, status

from .. import views
from ..contract import KeepIn, NewsItemOut, NewsOut, NewsSourcesOut, Problem
from ..news import store as news_store
from ..news import views as news_views

router = APIRouter(tags=["news"])

MAX_LIMIT = 1000


def _retention(request: Request) -> timedelta:
    return timedelta(days=request.app.state.settings.news_retention_days)


@router.get("/news", response_model=NewsOut, responses={422: {"model": Problem}})
async def news(
    request: Request,
    minutes: int | None = Query(
        default=None, ge=1, le=60 * 24 * 60, description="the last N minutes; wins over `hours`"
    ),
    hours: int | None = Query(default=None, ge=1, le=24 * 60),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    source: list[str] | None = Query(default=None),
    q: str | None = Query(default=None, min_length=1, max_length=200),
    kept: bool = Query(default=False, description="only the kept headlines, whatever their age"),
    limit: int = Query(default=300, ge=1, le=MAX_LIMIT),
) -> NewsOut:
    """Headlines newest first — by publication, and by first sight where the feed gave no time."""
    start = end = None
    if not kept:
        start, end = views.window(
            hours=None if minutes is not None else hours,
            minutes=minutes,
            since=since,
            until=until,
            default_hours=6,
        )
        if start >= end:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=Problem(
                    detail=f"the window ends before it starts: {start.isoformat()} to {end.isoformat()}",
                    cause="request",
                ).model_dump(),
            )
    async with request.app.state.pool.acquire() as conn:
        return await news_views.news(
            conn,
            start=start,
            end=end,
            sources=source,
            text=q,
            kept_only=kept,
            limit=limit,
            retention=_retention(request),
        )


@router.get("/news/sources", response_model=NewsSourcesOut)
async def news_sources(request: Request) -> NewsSourcesOut:
    """Every declared feed, including one that has never answered, with its last day of delays."""
    settings = request.app.state.settings
    async with request.app.state.pool.acquire() as conn:
        return await news_views.sources_state(
            conn,
            now=datetime.now(UTC),
            tick_seconds=settings.news_tick_seconds,
            retention_days=settings.news_retention_days,
        )


@router.put("/news/keep", response_model=NewsItemOut, responses={404: {"model": Problem}})
async def keep(request: Request, body: KeepIn) -> NewsItemOut:
    """Keep a headline past retention, or let it go again. Idempotent both ways."""
    async with request.app.state.pool.acquire() as conn:
        found = await news_store.set_kept(
            conn, body.source, body.external_id, keep=body.keep, at=datetime.now(UTC)
        )
    if found is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=Problem(
                detail=f"no headline {body.external_id!r} from {body.source!r}", cause="request"
            ).model_dump(),
        )
    return news_views.item_out(found, retention=_retention(request))
