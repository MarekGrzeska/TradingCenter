"""Every statement the news runs against the archive's database. Plain SQL, like the rest of the package."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from tc_runtime.db import Conn

from .models import FeedItem, NewsItem, SourceRow

_ITEM_COLUMNS = """
    source, external_id, publisher, title, summary, url,
    published_at, first_seen_at, previous_fetch_at, kept_at
"""

# The contract's order: newest by publication, and by first sight where the feed gave no time.
_ORDER = "COALESCE(published_at, first_seen_at)"


def _item(row) -> NewsItem:
    return NewsItem(**dict(row))


async def declare_sources(conn: Conn, source_ids: Sequence[str]) -> None:
    """A state row per declared feed before the first fetch, so a feed that never answers is still listed."""
    await conn.execute(
        "INSERT INTO news_sources (source) SELECT unnest($1::text[]) ON CONFLICT (source) DO NOTHING",
        list(source_ids),
    )


async def previous_success(conn: Conn, source: str) -> datetime | None:
    """Locked, so two passes over one feed cannot both measure against the same previous fetch."""
    return await conn.fetchval(
        "SELECT last_success_at FROM news_sources WHERE source = $1 FOR UPDATE", source
    )


async def insert_items(
    conn: Conn,
    source: str,
    items: Sequence[FeedItem],
    *,
    seen_at: datetime,
    previous_fetch_at: datetime | None,
) -> int:
    """New headlines inserted, the rest ignored. `DO NOTHING`: the moment of first sight is a measurement,
    and a feed rewriting an item's title or time must not move it."""
    # The first of any repeated identifier within one document, as the order the feed gave it.
    unique = list({item.external_id: item for item in reversed(items)}.values())[::-1]
    if not unique:
        return 0
    rows = await conn.fetch(
        """
        INSERT INTO news_items (
            source, external_id, publisher, title, summary, url,
            published_at, first_seen_at, previous_fetch_at
        )
        SELECT $1, external_id, publisher, title, summary, url, published_at, $2, $3
        FROM unnest($4::text[], $5::text[], $6::text[], $7::text[], $8::text[], $9::timestamptz[])
            AS t(external_id, publisher, title, summary, url, published_at)
        ON CONFLICT (source, external_id) DO NOTHING
        RETURNING id
        """,
        source,
        seen_at,
        previous_fetch_at,
        [item.external_id for item in unique],
        [item.publisher for item in unique],
        [item.title for item in unique],
        [item.summary for item in unique],
        [item.url for item in unique],
        [item.published_at for item in unique],
    )
    return len(rows)


async def record_success(
    conn: Conn, source: str, *, at: datetime, newest_published_at: datetime | None
) -> None:
    await conn.execute(
        """
        UPDATE news_sources
        SET last_attempt_at = $2, last_success_at = $2,
            newest_published_at = COALESCE($3, newest_published_at)
        WHERE source = $1
        """,
        source,
        at,
        newest_published_at,
    )


async def record_failure(conn: Conn, source: str, *, at: datetime, reason: str) -> None:
    """`last_success_at` untouched: a failed fetch moves nothing forward."""
    await conn.execute(
        """
        UPDATE news_sources
        SET last_attempt_at = $2, last_failure_at = $2, last_failure = $3
        WHERE source = $1
        """,
        source,
        at,
        reason[:500],
    )


async def source_rows(conn: Conn) -> list[SourceRow]:
    rows = await conn.fetch(
        """
        SELECT source, last_attempt_at, last_success_at, last_failure_at, last_failure,
               newest_published_at
        FROM news_sources
        """
    )
    return [SourceRow(**dict(row)) for row in rows]


async def seen_since(
    conn: Conn, since: datetime
) -> list[tuple[str, datetime | None, datetime, datetime | None]]:
    """The three moments of every headline first seen since `since` — what a source's figures are made of."""
    rows = await conn.fetch(
        """
        SELECT source, published_at, first_seen_at, previous_fetch_at
        FROM news_items
        WHERE first_seen_at >= $1
        """,
        since,
    )
    return [
        (row["source"], row["published_at"], row["first_seen_at"], row["previous_fetch_at"])
        for row in rows
    ]


async def items_in_window(
    conn: Conn,
    *,
    start: datetime,
    end: datetime,
    sources: Sequence[str] | None,
    text: str | None,
    limit: int,
) -> list[NewsItem]:
    """Newest first. Asked for one more than `limit`, so the caller can say the list is cut."""
    rows = await conn.fetch(
        f"""
        SELECT {_ITEM_COLUMNS}
        FROM news_items
        WHERE {_ORDER} >= $1 AND {_ORDER} <= $2
          AND ($3::text[] IS NULL OR source = ANY($3))
          AND ($4::text IS NULL OR strpos(lower(title || ' ' || summary), lower($4)) > 0)
        ORDER BY {_ORDER} DESC, id DESC
        LIMIT $5
        """,
        start,
        end,
        list(sources) if sources else None,
        text,
        limit,
    )
    return [_item(row) for row in rows]


async def kept_items(conn: Conn, *, limit: int) -> list[NewsItem]:
    rows = await conn.fetch(
        f"""
        SELECT {_ITEM_COLUMNS}
        FROM news_items
        WHERE kept_at IS NOT NULL
        ORDER BY {_ORDER} DESC, id DESC
        LIMIT $1
        """,
        limit,
    )
    return [_item(row) for row in rows]


async def set_kept(
    conn: Conn, source: str, external_id: str, *, keep: bool, at: datetime
) -> NewsItem | None:
    """Idempotent both ways: keeping a kept headline keeps the moment it was first kept."""
    row = await conn.fetchrow(
        f"""
        UPDATE news_items
        SET kept_at = CASE WHEN $3 THEN COALESCE(kept_at, $4) ELSE NULL END
        WHERE source = $1 AND external_id = $2
        RETURNING {_ITEM_COLUMNS}
        """,
        source,
        external_id,
        keep,
        at,
    )
    return None if row is None else _item(row)


async def sweep(conn: Conn, *, before: datetime) -> int:
    """Retention. A kept headline is never swept, however old."""
    result = await conn.execute(
        "DELETE FROM news_items WHERE first_seen_at < $1 AND kept_at IS NULL", before
    )
    return int(result.split()[-1])
