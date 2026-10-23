"""How the topics' searches went. Read-only: the loop writes it, and nobody — not the operator, not the agent — edits it."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from .. import store
from ..contract import TopicRunOut, TopicRunsOut
from .deps import connection

router = APIRouter(tags=["topic runs"])

MAX_LIMIT = 200


@router.get("/topic-runs", response_model=TopicRunsOut)
async def topic_runs(
    request: Request,
    topic_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=MAX_LIMIT),
) -> TopicRunsOut:
    """Searches of the topics, newest first — all of them or one topic's. Reading it asks nobody anything."""
    async with connection(request.app.state.pool) as conn:
        found = await store.list_runs(conn, topic_id=topic_id, limit=limit)
    return TopicRunsOut(runs=[TopicRunOut.of(run) for run in found], retention_days=store.RUN_RETENTION.days)
