"""What the routes answer with, assembled from the store and the latency rules."""

from __future__ import annotations

from datetime import datetime, timedelta

from tc_runtime.db import Conn

from ..contract import NewsItemOut, NewsOut, NewsSourceOut, NewsSourcesOut
from . import latency, store
from .models import NewsItem, SourceFigures, SourceRow
from .sources import SOURCES, NewsSource

FIGURES_WINDOW = timedelta(hours=24)
STALE_AFTER_INTERVALS = 6
NO_FIGURES = SourceFigures(0, 0, None, None, None, None)


def item_out(item: NewsItem, *, retention: timedelta) -> NewsItemOut:
    measured = latency.delay(
        published_at=item.published_at,
        first_seen_at=item.first_seen_at,
        previous_fetch_at=item.previous_fetch_at,
    )
    return NewsItemOut(
        source=item.source,
        external_id=item.external_id,
        publisher=item.publisher,
        title=item.title,
        summary=item.summary,
        content=item.content,
        url=item.url,
        published_at=item.published_at,
        first_seen_at=item.first_seen_at,
        previous_fetch_at=item.previous_fetch_at,
        delay_min_seconds=measured.lower_seconds,
        delay_max_seconds=measured.upper_seconds,
        delay_unmeasured=None if measured.unmeasured is None else measured.unmeasured.value,
        kept_at=item.kept_at,
        expires_at=None if item.kept_at is not None else item.first_seen_at + retention,
    )


def status(source: NewsSource, row: SourceRow | None, *, now: datetime) -> str:
    if row is None or row.last_attempt_at is None:
        return "pending"
    stale_after = timedelta(seconds=source.interval_seconds * STALE_AFTER_INTERVALS)
    if row.last_success_at is None or now - row.last_success_at > stale_after:
        return "stale"
    if row.last_failure_at is not None and row.last_failure_at > row.last_success_at:
        return "failing"
    return "ok"


async def news(
    conn: Conn,
    *,
    start: datetime | None,
    end: datetime | None,
    sources: list[str] | None,
    text: str | None,
    kept_only: bool,
    limit: int,
    retention: timedelta,
) -> NewsOut:
    if kept_only:
        found = await store.kept_items(conn, limit=limit + 1)
    else:
        assert start is not None and end is not None
        found = await store.items_in_window(
            conn, start=start, end=end, sources=sources, text=text, limit=limit + 1
        )
    shown = found[:limit]
    return NewsOut(
        items=[item_out(item, retention=retention) for item in shown],
        count=len(shown),
        truncated=len(found) > limit,
        window_from=None if kept_only else start,
        window_to=None if kept_only else end,
    )


async def sources_state(
    conn: Conn, *, now: datetime, tick_seconds: int, retention_days: int
) -> NewsSourcesOut:
    rows = {row.source: row for row in await store.source_rows(conn)}
    day = await store.source_figures(
        conn, now - FIGURES_WINDOW, tolerance_seconds=latency.CLOCK_TOLERANCE.total_seconds()
    )
    answered = []
    for source in SOURCES:
        row = rows.get(source.id)
        figures = day.get(source.id) or NO_FIGURES
        answered.append(
            NewsSourceOut(
                source=source.id,
                publisher=source.publisher,
                url=source.url,
                interval_seconds=source.interval_seconds,
                status=status(source, row, now=now),  # type: ignore[arg-type]
                last_attempt_at=row.last_attempt_at if row else None,
                last_success_at=row.last_success_at if row else None,
                last_failure_at=row.last_failure_at if row else None,
                last_failure=row.last_failure if row else None,
                newest_published_at=row.newest_published_at if row else None,
                items_24h=figures.items,
                unmeasured_24h=figures.unmeasured,
                delay_min_median_seconds=figures.lower_median,
                delay_min_p90_seconds=figures.lower_p90,
                delay_max_median_seconds=figures.upper_median,
                delay_max_p90_seconds=figures.upper_p90,
            )
        )
    return NewsSourcesOut(
        sources=answered,
        figures_window_hours=int(FIGURES_WINDOW.total_seconds() // 3600),
        tick_seconds=tick_seconds,
        stale_after_intervals=STALE_AFTER_INTERVALS,
        retention_days=retention_days,
    )
