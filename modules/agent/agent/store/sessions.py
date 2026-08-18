"""Sessions — the rozmowa itself, and the title derived from its first question.

`deleted_at IS NULL` rides on every read here, which is what makes a removed session
answer like a missing one through every route at once.
"""

from __future__ import annotations

import asyncpg
from tc_runtime.db import Conn, fetch_one

from ..models import (
    Session,
)

# How much of the first message becomes the session's title (specs/agent-chat, "Tytuł
# powstaje z pierwszego pytania"). Long enough to be recognisable in a narrow list,
# short enough that one does not crowd out its neighbours.
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

# `deleted_at IS NULL` rides on every read of a session, here and below. One condition in
# one place is what makes a removed rozmowa answer like a missing one everywhere at once
# — GET, PATCH, the transcript and a new turn all reach the session through this — rather
# than each route remembering to check.
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

# The operator's own name for a rozmowa. It overwrites whatever `derive_title` put there
# and is never overwritten back: `_TOUCH_SESSION` below only fills a title that is still
# NULL, so a renamed session keeps its name for every turn after.
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
    """`None` for a session that does not exist, for one owned by someone else, and for
    one the operator removed — all three are indistinguishable to a caller on purpose
    (specs/agent-browser-access, "Odmowa dostępu do cudzej sesji MUST być nieodróżnialna
    od odpowiedzi o sesji nieistniejącej")."""
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
    """False for a session that does not exist, belongs to someone else, or was already
    removed — the caller cannot tell which, same as `get_session`.

    The row is stamped, not deleted: `usage` references it, and a rozmowa removed from the
    list must not remove what it cost from the ledger (specs/agent-usage, "Skasowanie
    rozmowy nie zmniejsza rachunku"). The transcript stays in `messages` too, unreachable
    through this module's API — actually erasing text is a different operation from
    tidying a list, and nothing here claims to do it."""
    row = await conn.fetchrow(_SOFT_DELETE_SESSION, session_id, owner_principal)
    return row is not None
