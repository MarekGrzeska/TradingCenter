"""How the topics' searches went. Read-only: the loop writes it, and nobody — not the operator, not the agent — edits it."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request, status

from .. import store, views
from ..contract import Problem, TopicRunOut, TopicRunsOut
from .deps import connection

router = APIRouter(tags=["topic runs"])

MAX_LIMIT = 200


@router.get("/topic-runs", response_model=TopicRunsOut, responses={422: {"model": Problem}})
async def topic_runs(
    request: Request,
    topic_id: int | None = Query(default=None),
    since: datetime | None = Query(default=None, description="from this moment, included; without a zone it is UTC"),
    until: datetime | None = Query(default=None, description="to this moment, excluded; without a zone it is UTC"),
    limit: int = Query(default=100, ge=1, le=MAX_LIMIT),
) -> TopicRunsOut:
    """Searches of the topics, newest first — all of them or one topic's, within a range of time if asked. Reading it asks
    nobody anything."""
    start, end = views.aware(since), views.aware(until)
    if start is not None and end is not None and start >= end:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=Problem(
                detail=f"the range ends before it starts: {start.isoformat()} to {end.isoformat()}", cause="request"
            ).model_dump(),
        )
    async with connection(request.app.state.pool) as conn:
        found = await store.list_runs(conn, topic_id=topic_id, since=start, until=end, limit=limit)
    return TopicRunsOut(runs=[TopicRunOut.of(run) for run in found], retention_days=store.RUN_RETENTION.days)
