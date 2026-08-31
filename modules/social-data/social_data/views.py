"""Reads that both surfaces make, in one place — the REST routes and the tools ask the same three
questions, and answering them twice is how the two would come to disagree."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tc_runtime.db import Conn

from . import store
from .contract import PostOut, PostsOut, SourceStateOut, StateOut
from .models import SourceState


def window(
    *,
    hours: int | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    default_hours: int,
    now: datetime | None = None,
) -> tuple[datetime, datetime]:
    """The window a caller asked for, as two instants. `hours` and an explicit range are two ways of
    saying the same thing, and the explicit one wins where both arrive."""
    end = until or (now or datetime.now(UTC))
    if since is not None:
        return since, end
    return end - timedelta(hours=hours or default_hours), end


def is_stale(
    state: SourceState, *, interval_seconds: int, after_ticks: int, now: datetime
) -> bool:
    """Whether the archive has stopped hearing from a source. Measured from the last success and
    not from the last attempt: a source failing every minute is silent, however busy the loop is."""
    last = state.last_success_at or state.collecting_since
    return now - last > timedelta(seconds=interval_seconds * after_ticks)


async def posts(
    conn: Conn,
    *,
    start: datetime,
    end: datetime,
    source: str | None = None,
    min_score: int | None = None,
    topic: str | None = None,
    limit: int,
) -> PostsOut:
    found = await store.posts_in_window(
        conn, start=start, end=end, source=source, min_score=min_score, topic=topic, limit=limit
    )
    return PostsOut(
        posts=[PostOut.of(post) for post in found],
        count=len(found),
        window_from=start,
        window_to=end,
    )


async def state(conn: Conn, settings, *, now: datetime | None = None) -> StateOut:
    moment = now or datetime.now(UTC)
    states = await store.collection_states(conn)
    counted = await store.count_in_window(
        conn, start=moment - timedelta(hours=settings.collect_window_hours), end=moment
    )
    return StateOut(
        sources=[
            SourceStateOut.of(
                source,
                stale=is_stale(
                    source,
                    interval_seconds=settings.collect_interval_seconds,
                    after_ticks=settings.stale_after_ticks,
                    now=moment,
                ),
            )
            for source in states
        ],
        posts_in_window=counted,
        window_hours=settings.collect_window_hours,
        collect_interval_seconds=settings.collect_interval_seconds,
        model_configured=settings.model_configured,
    )
