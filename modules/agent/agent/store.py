"""Reading and writing sessions, their transcript and their usage — the only door to
those three tables, same shape as `market_data/store.py`: asyncpg directly, no ORM in
the runtime path.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import asyncpg

from .db import Conn, fetch_one
from .models import Message, Role, Session, Usage, UsageAggregate

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

_SELECT_SESSION = """
    SELECT id, owner_principal, title, current_model_id, created_at, last_active_at
      FROM sessions
     WHERE id = $1 AND owner_principal = $2
"""

# `title IS NOT NULL` is the whole enforcement of "Pusta sesja nie zaśmieca historii" —
# a session earns its place here the moment its first message sets this column.
_SELECT_SESSIONS_FOR_OWNER = """
    SELECT id, owner_principal, title, current_model_id, created_at, last_active_at
      FROM sessions
     WHERE owner_principal = $1 AND title IS NOT NULL
     ORDER BY last_active_at DESC
"""

_UPDATE_SESSION_MODEL = """
    UPDATE sessions SET current_model_id = $2
     WHERE id = $1 AND owner_principal = $3
    RETURNING id, owner_principal, title, current_model_id, created_at, last_active_at
"""

_SELECT_MESSAGES = """
    SELECT id, session_id, role, content, model_id, prompt_version, incomplete, created_at
      FROM messages
     WHERE session_id = $1
     ORDER BY id
"""

_INSERT_MESSAGE = """
    INSERT INTO messages (session_id, role, content, model_id, prompt_version, incomplete)
    VALUES ($1, $2, $3, $4, $5, $6)
    RETURNING id, session_id, role, content, model_id, prompt_version, incomplete, created_at
"""

_TOUCH_SESSION = """
    UPDATE sessions SET last_active_at = now(), title = COALESCE(title, $2)
     WHERE id = $1
"""

_INSERT_USAGE = """
    INSERT INTO usage (
        session_id, message_id, model_id,
        input_tokens, output_tokens, cached_tokens, reasoning_tokens,
        input_rate_per_1m, output_rate_per_1m, cost
    )
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
    RETURNING id, session_id, message_id, model_id,
              input_tokens, output_tokens, cached_tokens, reasoning_tokens,
              input_rate_per_1m, output_rate_per_1m, cost, created_at
"""


def _session_from_row(row: asyncpg.Record) -> Session:
    return Session(**dict(row))


def _message_from_row(row: asyncpg.Record) -> Message:
    data = dict(row)
    data["role"] = Role(data["role"])
    return Message(**data)


def _usage_from_row(row: asyncpg.Record) -> Usage:
    return Usage(**dict(row))


async def create_session(
    conn: Conn, *, owner_principal: str, model_id: str
) -> Session:
    row = await fetch_one(conn, _INSERT_SESSION, owner_principal, model_id)
    return _session_from_row(row)


async def get_session(
    conn: Conn, *, session_id: int, owner_principal: str
) -> Session | None:
    """`None` for a session that does not exist *and* for one owned by someone else —
    the two are indistinguishable to a caller on purpose (specs/agent-browser-access,
    "Odmowa dostępu do cudzej sesji MUST być nieodróżnialna od odpowiedzi o sesji
    nieistniejącej")."""
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


async def get_messages(conn: Conn, *, session_id: int) -> list[Message]:
    rows = await conn.fetch(_SELECT_MESSAGES, session_id)
    return [_message_from_row(row) for row in rows]


async def append_operator_message(
    conn: Conn, *, session_id: int, content: str
) -> Message:
    """Written before the model is ever called (specs/agent-chat, "Wypowiedź operatora
    MUST być zapisana zanim moduł zawoła model") — what the operator typed survives a
    failed call. The session's title is set here if this is its first exchange, in the
    same transaction as the message it is derived from."""
    async with conn.transaction():
        row = await fetch_one(
            conn, _INSERT_MESSAGE, session_id, Role.OPERATOR.value, content, None, None, False
        )
        await conn.execute(_TOUCH_SESSION, session_id, derive_title(content))
    return _message_from_row(row)


async def append_agent_message(
    conn: Conn,
    *,
    session_id: int,
    content: str,
    model_id: str,
    prompt_version: str,
    incomplete: bool,
) -> Message:
    async with conn.transaction():
        row = await fetch_one(
            conn,
            _INSERT_MESSAGE,
            session_id,
            Role.AGENT.value,
            content,
            model_id,
            prompt_version,
            incomplete,
        )
        await conn.execute("UPDATE sessions SET last_active_at = now() WHERE id = $1", session_id)
    return _message_from_row(row)


async def record_usage(
    conn: Conn,
    *,
    session_id: int,
    message_id: int,
    model_id: str,
    input_tokens: int | None,
    output_tokens: int | None,
    cached_tokens: int | None,
    reasoning_tokens: int | None,
    input_rate_per_1m: Decimal,
    output_rate_per_1m: Decimal,
) -> Usage:
    """The one place a cost is computed, and the only moment it ever is — never again at
    read time (specs/agent-usage, "Koszt jest przypisany do wiersza w chwili zapisu")."""
    cost = None
    if input_tokens is not None and output_tokens is not None:
        cost = (Decimal(input_tokens) / 1_000_000 * input_rate_per_1m) + (
            Decimal(output_tokens) / 1_000_000 * output_rate_per_1m
        )
    row = await fetch_one(
        conn,
        _INSERT_USAGE,
        session_id,
        message_id,
        model_id,
        input_tokens,
        output_tokens,
        cached_tokens,
        reasoning_tokens,
        input_rate_per_1m,
        output_rate_per_1m,
        cost,
    )
    return _usage_from_row(row)


# --- zbiorczy odczyt zużycia (specs/agent-usage, "Zużycie da się odczytać zbiorczo") ---
#
# Every aggregate is scoped to the caller's own sessions (the `JOIN sessions` filters on
# `owner_principal`) — usage belongs to whoever the session belongs to, same as the
# transcript does. `SUM` ignores NULL rows on its own; `unknown_count` is what a caller
# would otherwise never learn it silently dropped.

_AGGREGATE_COLUMNS = """
    COALESCE(SUM(u.input_tokens), 0)::bigint AS input_tokens,
    COALESCE(SUM(u.output_tokens), 0)::bigint AS output_tokens,
    COALESCE(SUM(u.cost), 0) AS cost,
    COUNT(*) FILTER (WHERE u.cost IS NULL)::bigint AS unknown_count
"""

_AGGREGATE_WHERE = """
    WHERE s.owner_principal = $1
      AND ($2::timestamptz IS NULL OR u.created_at >= $2)
      AND ($3::timestamptz IS NULL OR u.created_at < $3)
"""

_USAGE_BY_MODEL = f"""
    SELECT u.model_id AS key, {_AGGREGATE_COLUMNS}
      FROM usage u JOIN sessions s ON s.id = u.session_id
    {_AGGREGATE_WHERE}
     GROUP BY u.model_id
     ORDER BY u.model_id
"""

_USAGE_BY_SESSION = f"""
    SELECT u.session_id::text AS key, {_AGGREGATE_COLUMNS}
      FROM usage u JOIN sessions s ON s.id = u.session_id
    {_AGGREGATE_WHERE}
     GROUP BY u.session_id
     ORDER BY u.session_id
"""

_USAGE_BY_DAY = f"""
    SELECT to_char(date_trunc('day', u.created_at), 'YYYY-MM-DD') AS key, {_AGGREGATE_COLUMNS}
      FROM usage u JOIN sessions s ON s.id = u.session_id
    {_AGGREGATE_WHERE}
     GROUP BY 1
     ORDER BY 1
"""

_USAGE_TOTAL_COST = f"""
    SELECT COALESCE(SUM(u.cost), 0) AS total_cost
      FROM usage u JOIN sessions s ON s.id = u.session_id
    {_AGGREGATE_WHERE}
"""


def _aggregate_from_row(row: asyncpg.Record) -> UsageAggregate:
    return UsageAggregate(**dict(row))


async def usage_by_model(
    conn: Conn, *, owner_principal: str, since: datetime | None, until: datetime | None
) -> list[UsageAggregate]:
    rows = await conn.fetch(_USAGE_BY_MODEL, owner_principal, since, until)
    return [_aggregate_from_row(row) for row in rows]


async def usage_by_session(
    conn: Conn, *, owner_principal: str, since: datetime | None, until: datetime | None
) -> list[UsageAggregate]:
    rows = await conn.fetch(_USAGE_BY_SESSION, owner_principal, since, until)
    return [_aggregate_from_row(row) for row in rows]


async def usage_by_day(
    conn: Conn, *, owner_principal: str, since: datetime | None, until: datetime | None
) -> list[UsageAggregate]:
    rows = await conn.fetch(_USAGE_BY_DAY, owner_principal, since, until)
    return [_aggregate_from_row(row) for row in rows]


async def usage_total_cost(
    conn: Conn, *, owner_principal: str, since: datetime | None, until: datetime | None
) -> Decimal:
    row = await fetch_one(conn, _USAGE_TOTAL_COST, owner_principal, since, until)
    return row["total_cost"]
