"""Sessions — the rozmowa itself, and the title derived from its first question. `deleted_at IS NULL` rides
on every read here, which makes a removed session answer like a missing one through every route."""

from __future__ import annotations

import asyncpg
from tc_runtime.db import Conn, fetch_one

from ..models import (
    Session,
)

# How much of the first message becomes the session's title: long enough to be recognisable in a narrow
# list, short enough that one does not crowd out its neighbours.
_TITLE_MAX_CHARS = 60


def derive_title(first_message: str) -> str:
    collapsed = " ".join(first_message.split())
    if len(collapsed) <= _TITLE_MAX_CHARS:
        return collapsed
    return collapsed[: _TITLE_MAX_CHARS - 1].rstrip() + "…"


_INSERT_SESSION = """
    INSERT INTO sessions (owner_principal, current_model_id)
    VALUES ($1, $2)
    RETURNING id, owner_principal, title, current_model_id, created_at, last_active_at
"""

# `deleted_at IS NULL` rides on every read of a session. One condition in one place is what makes a removed
# rozmowa answer like a missing one everywhere at once, rather than each route remembering to check.
_SELECT_SESSION = """
    SELECT id, owner_principal, title, current_model_id, created_at, last_active_at
      FROM sessions
     WHERE id = $1 AND owner_principal = $2 AND deleted_at IS NULL
"""

# `title IS NOT NULL` is the whole enforcement of "Pusta sesja nie zaśmieca historii" —
# a session earns its place here the moment its first message sets this column.
_SELECT_SESSIONS_FOR_OWNER = """
    SELECT id, owner_principal, title, current_model_id, created_at, last_active_at
      FROM sessions
     WHERE owner_principal = $1 AND title IS NOT NULL AND deleted_at IS NULL
     ORDER BY last_active_at DESC
"""

_UPDATE_SESSION_MODEL = """
    UPDATE sessions SET current_model_id = $2
     WHERE id = $1 AND owner_principal = $3 AND deleted_at IS NULL
    RETURNING id, owner_principal, title, current_model_id, created_at, last_active_at
"""

# The operator's own name for a rozmowa. It overwrites whatever `derive_title` put there and is never
# overwritten back: `_TOUCH_SESSION` only fills a title that is still NULL.
_UPDATE_SESSION_TITLE = """
    UPDATE sessions SET title = $2
     WHERE id = $1 AND owner_principal = $3 AND deleted_at IS NULL
    RETURNING id, owner_principal, title, current_model_id, created_at, last_active_at
"""

# `deleted_at IS NULL` in the WHERE, not just the stamp: deleting twice returns no row,
# so the route answers 404 the second time instead of silently moving the timestamp.
_SOFT_DELETE_SESSION = """
    UPDATE sessions SET deleted_at = now()
     WHERE id = $1 AND owner_principal = $2 AND deleted_at IS NULL
    RETURNING id
"""

def _session_from_row(row: asyncpg.Record) -> Session:
    return Session(**dict(row))


async def create_session(
    conn: Conn, *, owner_principal: str, model_id: str
) -> Session:
    row = await fetch_one(conn, _INSERT_SESSION, owner_principal, model_id)
    return _session_from_row(row)


async def get_session(
    conn: Conn, *, session_id: int, owner_principal: str
) -> Session | None:
    """`None` for a session that does not exist, one owned by someone else, and one the operator removed —
    all three indistinguishable to a caller on purpose."""
    row = await conn.fetchrow(_SELECT_SESSION, session_id, owner_principal)
    return _session_from_row(row) if row else None


async def list_sessions(conn: Conn, *, owner_principal: str) -> list[Session]:
    rows = await conn.fetch(_SELECT_SESSIONS_FOR_OWNER, owner_principal)
    return [_session_from_row(row) for row in rows]


async def set_session_model(
    conn: Conn, *, session_id: int, owner_principal: str, model_id: str
) -> Session | None:
    row = await conn.fetchrow(_UPDATE_SESSION_MODEL, session_id, model_id, owner_principal)
    return _session_from_row(row) if row else None


async def set_session_title(
    conn: Conn, *, session_id: int, owner_principal: str, title: str
) -> Session | None:
    row = await conn.fetchrow(_UPDATE_SESSION_TITLE, session_id, title, owner_principal)
    return _session_from_row(row) if row else None


async def delete_session(conn: Conn, *, session_id: int, owner_principal: str) -> bool:
    """False for a session that does not exist, belongs to someone else, or was already removed. The row is
    stamped, not deleted: `usage` references it, and removing a rozmowa must not remove what it cost."""
    row = await conn.fetchrow(_SOFT_DELETE_SESSION, session_id, owner_principal)
    return row is not None
