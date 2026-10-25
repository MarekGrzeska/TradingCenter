"""The only door to this package's tables for strategies and their revisions. Nothing here updates a revision or deletes
anything: a revision is the next row, and a strategy is archived."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

import asyncpg
from tc_runtime.db import Conn

from .document import SCHEMA_VERSION, Checked

Author = Literal["operator", "agent"]


class NotFound(Exception):
    pass


class Conflict(Exception):
    """A save based on a revision that is no longer the latest: whoever saved in between would be silently undone."""

    def __init__(self, latest: int) -> None:
        super().__init__(latest)
        self.latest = latest


def decoded(value: Any) -> Any:
    """A `jsonb` column as the value it holds. asyncpg hands it back as text unless a codec says otherwise."""
    return json.loads(value) if isinstance(value, str) else value


@dataclass(frozen=True)
class Saved:
    strategy_id: int
    revision: int
    created: bool


async def create(pool: asyncpg.Pool, checked: Checked, author: Author) -> Saved:
    async with pool.acquire() as conn, conn.transaction():
        strategy_id = await conn.fetchval(
            "INSERT INTO strategies (name) VALUES ($1) RETURNING id", checked.document.name
        )
        await _insert_revision(conn, strategy_id, 1, checked, author)
        # The new strategy's draft became this strategy; left, it would come back the next time "new" is opened.
        await conn.execute("DELETE FROM strategy_drafts WHERE strategy_id IS NULL")
    return Saved(strategy_id, 1, True)


async def save_revision(
    pool: asyncpg.Pool, strategy_id: int, checked: Checked, author: Author, based_on: int | None = None
) -> Saved:
    """The next revision, or the latest one unchanged when the content is the same. The strategy's row is locked for the
    length of it, so two saves at once take numbers one after the other instead of the same one. `based_on`, when given,
    is the revision the change was made to; a different latest one is a `Conflict` (design D3)."""
    async with pool.acquire() as conn, conn.transaction():
        found = await conn.fetchval("SELECT id FROM strategies WHERE id = $1 FOR UPDATE", strategy_id)
        if found is None:
            raise NotFound(strategy_id)
        # A save ends the draft, whether or not the content was new: the editor now shows what is saved.
        await conn.execute("DELETE FROM strategy_drafts WHERE strategy_id = $1", strategy_id)
        latest = await conn.fetchrow(
            "SELECT n, content_hash FROM strategy_revisions WHERE strategy_id = $1 ORDER BY n DESC LIMIT 1", strategy_id
        )
        if latest is not None and latest["content_hash"] == checked.hash:
            return Saved(strategy_id, latest["n"], False)
        if based_on is not None and latest is not None and latest["n"] != based_on:
            raise Conflict(latest["n"])
        n = 1 if latest is None else latest["n"] + 1
        await _insert_revision(conn, strategy_id, n, checked, author)
        await conn.execute("UPDATE strategies SET name = $2 WHERE id = $1", strategy_id, checked.document.name)
    return Saved(strategy_id, n, True)


async def _insert_revision(conn: Conn, strategy_id: int, n: int, checked: Checked, author: Author) -> None:
    await conn.execute(
        "INSERT INTO strategy_revisions (strategy_id, n, document, content_hash, schema_version, author) "
        "VALUES ($1, $2, $3::jsonb, $4, $5, $6)",
        strategy_id, n, json.dumps(checked.canonical), checked.hash, SCHEMA_VERSION, author,
    )


_SUMMARY = """
    SELECT s.id, s.name, s.created_at, s.archived_at, r.n AS latest_revision, r.author AS latest_author,
           r.created_at AS changed_at, r.document->>'symbol' AS symbol, r.document->>'timeframe' AS timeframe,
           (SELECT count(*) FROM runs u WHERE u.strategy_id = s.id AND u.status = 'done') AS trials, s.conversation_id
    FROM strategies s
    CROSS JOIN LATERAL (
        SELECT n, author, created_at, document FROM strategy_revisions
        WHERE strategy_id = s.id ORDER BY n DESC LIMIT 1
    ) r
"""


@dataclass(frozen=True)
class Summary:
    id: int
    name: str
    created_at: datetime
    archived_at: datetime | None
    latest_revision: int
    latest_author: str
    changed_at: datetime
    symbol: str
    timeframe: str
    trials: int
    conversation_id: int | None


def _summary(row: asyncpg.Record) -> Summary:
    return Summary(
        row["id"], row["name"], row["created_at"], row["archived_at"], row["latest_revision"], row["latest_author"],
        row["changed_at"], row["symbol"], row["timeframe"], row["trials"], row["conversation_id"],
    )


async def list_strategies(conn: Conn, *, archived: bool = False) -> list[Summary]:
    """The default list leaves archived strategies out; `archived=True` lists only them."""
    condition = "s.archived_at IS NOT NULL" if archived else "s.archived_at IS NULL"
    # Last changed first: the strategy the agent just revised is the one the operator is looking for.
    rows = await conn.fetch(f"{_SUMMARY} WHERE {condition} ORDER BY r.created_at DESC, s.id DESC")
    return [_summary(row) for row in rows]


async def get_strategy(conn: Conn, strategy_id: int) -> Summary:
    row = await conn.fetchrow(f"{_SUMMARY} WHERE s.id = $1", strategy_id)
    if row is None:
        raise NotFound(strategy_id)
    return _summary(row)


@dataclass(frozen=True)
class Revision:
    strategy_id: int
    n: int
    document: dict[str, Any]
    content_hash: str
    schema_version: int
    author: str
    created_at: datetime


async def get_revision(conn: Conn, strategy_id: int, n: int | None = None) -> Revision:
    """Revision `n`, or the latest one."""
    row = await conn.fetchrow(
        "SELECT * FROM strategy_revisions WHERE strategy_id = $1 AND ($2::integer IS NULL OR n = $2) "
        "ORDER BY n DESC LIMIT 1",
        strategy_id, n,
    )
    if row is None:
        raise NotFound((strategy_id, n))
    return Revision(
        row["strategy_id"], row["n"], decoded(row["document"]), row["content_hash"], row["schema_version"],
        row["author"], row["created_at"],
    )


@dataclass(frozen=True)
class RevisionEntry:
    n: int
    author: str
    created_at: datetime
    content_hash: str


async def list_revisions(conn: Conn, strategy_id: int) -> list[RevisionEntry]:
    """Newest first, without documents. `NotFound` for a strategy that does not exist, never an empty list."""
    rows = await conn.fetch(
        "SELECT n, author, created_at, content_hash FROM strategy_revisions WHERE strategy_id = $1 ORDER BY n DESC",
        strategy_id,
    )
    if not rows:
        raise NotFound(strategy_id)
    return [RevisionEntry(row["n"], row["author"], row["created_at"], row["content_hash"]) for row in rows]


async def set_conversation(conn: Conn, strategy_id: int, conversation_id: int | None) -> Summary:
    """Which conversation the strategy is written in — not a revision, and not a trial."""
    found = await conn.fetchval(
        "UPDATE strategies SET conversation_id = $2 WHERE id = $1 RETURNING id", strategy_id, conversation_id
    )
    if found is None:
        raise NotFound(strategy_id)
    return await get_strategy(conn, strategy_id)


async def set_archived(conn: Conn, strategy_id: int, archived: bool) -> Summary:
    found = await conn.fetchval(
        "UPDATE strategies SET archived_at = CASE WHEN $2 THEN coalesce(archived_at, now()) END "
        "WHERE id = $1 RETURNING id",
        strategy_id, archived,
    )
    if found is None:
        raise NotFound(strategy_id)
    return await get_strategy(conn, strategy_id)
