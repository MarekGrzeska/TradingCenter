"""Every statement this module runs against its own database. Plain asyncpg, no ORM: the tables are
handwritten SQL and so are the queries, so a read is the statement it will actually run."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from tc_runtime.db import Conn, fetch_one

from .models import Operation, Post, RawPost, SourceState

# Every column a `Post` is built from, in one place: three queries select it and a fourth would
# have drifted from the others by a column within a month.
_POST_COLUMNS = """
    id, source, external_id, author, content, url, is_repost, published_at, fetched_at,
    translated_content, translated_model, translated_at,
    topics, impact_score, analysed_model, analysed_at
"""


def _post(row) -> Post:
    return Post(
        id=row["id"],
        source=row["source"],
        external_id=row["external_id"],
        author=row["author"],
        content=row["content"],
        url=row["url"],
        is_repost=row["is_repost"],
        published_at=row["published_at"],
        fetched_at=row["fetched_at"],
        translated_content=row["translated_content"],
        translated_model=row["translated_model"],
        translated_at=row["translated_at"],
        topics=tuple(row["topics"] or ()),
        impact_score=row["impact_score"],
        analysed_model=row["analysed_model"],
        analysed_at=row["analysed_at"],
    )


async def insert_new_posts(conn: Conn, posts: Sequence[RawPost]) -> int:
    """The posts this pass had not seen before, inserted; the rest ignored. Returns how many were new.

    `DO NOTHING` rather than an upsert: a post that is already here keeps the text it was collected
    with, and a source rewriting history is not something this archive follows.
    """
    if not posts:
        return 0
    rows = await conn.fetch(
        """
        INSERT INTO posts (source, external_id, author, content, url, is_repost, published_at)
        SELECT * FROM unnest(
            $1::text[], $2::text[], $3::text[], $4::text[], $5::text[],
            $6::boolean[], $7::timestamptz[]
        )
        ON CONFLICT (source, external_id) DO NOTHING
        RETURNING id
        """,
        [p.source for p in posts],
        [p.external_id for p in posts],
        [p.author for p in posts],
        [p.content for p in posts],
        [p.url for p in posts],
        [p.is_repost for p in posts],
        [p.published_at for p in posts],
    )
    return len(rows)


async def posts_in_window(
    conn: Conn,
    *,
    start: datetime,
    end: datetime,
    source: str | None = None,
    min_score: int | None = None,
    topic: str | None = None,
    limit: int = 200,
) -> list[Post]:
    """Newest first, always — the order is part of the contract, not whatever the plan produced."""
    rows = await conn.fetch(
        f"""
        SELECT {_POST_COLUMNS}
        FROM posts
        WHERE published_at >= $1 AND published_at <= $2
          AND ($3::text IS NULL OR source = $3)
          AND ($4::int IS NULL OR impact_score >= $4)
          AND ($5::text IS NULL OR topics @> ARRAY[$5]::text[])
        ORDER BY published_at DESC
        LIMIT $6
        """,
        start,
        end,
        source,
        min_score,
        topic,
        limit,
    )
    return [_post(row) for row in rows]


async def count_in_window(conn: Conn, *, start: datetime, end: datetime) -> int:
    row = await fetch_one(
        conn,
        "SELECT count(*) AS total FROM posts WHERE published_at >= $1 AND published_at <= $2",
        start,
        end,
    )
    return row["total"]


async def post_by_external_id(conn: Conn, source: str, external_id: str) -> Post | None:
    row = await conn.fetchrow(
        f"SELECT {_POST_COLUMNS} FROM posts WHERE source = $1 AND external_id = $2",
        source,
        external_id,
    )
    return None if row is None else _post(row)


async def posts_awaiting_translation(conn: Conn, *, since: datetime, limit: int) -> list[Post]:
    rows = await conn.fetch(
        f"""
        SELECT {_POST_COLUMNS}
        FROM posts
        WHERE translated_content IS NULL AND published_at >= $1
        ORDER BY published_at DESC
        LIMIT $2
        """,
        since,
        limit,
    )
    return [_post(row) for row in rows]


async def posts_awaiting_analysis(conn: Conn, *, since: datetime, limit: int) -> list[Post]:
    rows = await conn.fetch(
        f"""
        SELECT {_POST_COLUMNS}
        FROM posts
        WHERE impact_score IS NULL AND published_at >= $1
        ORDER BY published_at DESC
        LIMIT $2
        """,
        since,
        limit,
    )
    return [_post(row) for row in rows]


async def save_translation(conn: Conn, post_id: int, *, text: str, model: str) -> None:
    """Overwrites, stamp and all. A reading is current or it is replaced; there is no third state."""
    await conn.execute(
        """
        UPDATE posts
        SET translated_content = $2, translated_model = $3, translated_at = now()
        WHERE id = $1
        """,
        post_id,
        text,
        model,
    )


async def save_analysis(
    conn: Conn, post_id: int, *, topics: Sequence[str], score: int, model: str
) -> None:
    await conn.execute(
        """
        UPDATE posts
        SET topics = $2::text[], impact_score = $3, analysed_model = $4, analysed_at = now()
        WHERE id = $1
        """,
        post_id,
        list(topics),
        score,
        model,
    )


async def record_usage(
    conn: Conn,
    post_id: int,
    *,
    operation: Operation,
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> None:
    await conn.execute(
        """
        INSERT INTO model_usage (post_id, operation, model, input_tokens, output_tokens)
        VALUES ($1, $2, $3, $4, $5)
        """,
        post_id,
        operation.value,
        model,
        input_tokens,
        output_tokens,
    )


async def begin_collecting(conn: Conn, source: str, *, at: datetime | None = None) -> datetime:
    """The moment this archive started collecting a source, written once and never moved. Returns
    what is on the row, which for every pass after the first is the original value."""
    row = await fetch_one(
        conn,
        """
        INSERT INTO collection_state (source, collecting_since)
        VALUES ($1, COALESCE($2, now()))
        ON CONFLICT (source) DO UPDATE SET source = EXCLUDED.source
        RETURNING collecting_since
        """,
        source,
        at,
    )
    return row["collecting_since"]


async def record_collection_success(conn: Conn, source: str, *, at: datetime) -> None:
    await conn.execute(
        """
        UPDATE collection_state
        SET last_success_at = $2, consecutive_failures = 0, last_failure_reason = NULL
        WHERE source = $1
        """,
        source,
        at,
    )


async def record_collection_failure(
    conn: Conn, source: str, *, at: datetime, reason: str
) -> None:
    """`last_success_at` is deliberately untouched: a failed pass moves nothing forward, and a screen
    reading it has to keep saying how long ago the archive last heard anything."""
    await conn.execute(
        """
        UPDATE collection_state
        SET last_failure_at = $2,
            last_failure_reason = $3,
            consecutive_failures = collection_state.consecutive_failures + 1
        WHERE source = $1
        """,
        source,
        at,
        reason[:500],
    )


async def collection_states(conn: Conn) -> list[SourceState]:
    rows = await conn.fetch(
        """
        SELECT source, collecting_since, last_success_at, last_failure_at,
               last_failure_reason, consecutive_failures
        FROM collection_state
        ORDER BY source
        """
    )
    return [
        SourceState(
            source=row["source"],
            collecting_since=row["collecting_since"],
            last_success_at=row["last_success_at"],
            last_failure_at=row["last_failure_at"],
            last_failure_reason=row["last_failure_reason"],
            consecutive_failures=row["consecutive_failures"],
        )
        for row in rows
    ]
