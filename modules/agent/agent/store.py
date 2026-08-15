"""Reading and writing sessions, their transcript and their usage — the only door to
those three tables, same shape as `market_data/store.py`: asyncpg directly, no ORM in
the runtime path.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

import asyncpg

from .db import Conn, fetch_one
from .models import (
    Message,
    PromptRevision,
    RecordedCall,
    Role,
    Session,
    ToolCall,
    Usage,
    UsageAggregate,
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


# --- ślad wywołań narzędzi (specs/agent-tools, "Wywołanie narzędzia zostawia ślad") ---

_INSERT_TOOL_CALL = """
    INSERT INTO tool_calls (
        session_id, message_id, round_index, position,
        tool_name, arguments, outcome, result_text, duration_ms
    )
    VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9)
    RETURNING id, session_id, message_id, round_index, position,
              tool_name, arguments, outcome, result_text, duration_ms, created_at
"""

_TOOL_CALL_COLUMNS = """
    id, session_id, message_id, round_index, position,
    tool_name, arguments, outcome, result_text, duration_ms, created_at
"""

_SELECT_TOOL_CALLS = f"""
    SELECT {_TOOL_CALL_COLUMNS}
      FROM tool_calls
     WHERE message_id = $1
     ORDER BY round_index, position, id
"""

# `message_id` leads the ordering so the grouping below builds each message's list in the
# order the turn made the calls, in one pass and without sorting afterwards.
_SELECT_SESSION_TOOL_CALLS = f"""
    SELECT {_TOOL_CALL_COLUMNS}
      FROM tool_calls
     WHERE session_id = $1
     ORDER BY message_id, round_index, position, id
"""


def _tool_call_from_row(row: asyncpg.Record) -> ToolCall:
    data = dict(row)
    # asyncpg hands JSONB back as text unless a codec is registered; parsing here keeps
    # that decision in the one place that reads the column.
    data["arguments"] = json.loads(data["arguments"]) if isinstance(data["arguments"], str) else (
        data["arguments"]
    )
    return ToolCall(**data)


async def record_tool_calls(
    conn: Conn,
    *,
    session_id: int,
    message_id: int,
    calls: Sequence[RecordedCall],
) -> list[ToolCall]:
    """Written after the agent message exists, like usage rows and for the same reason:
    the id they hang off does not exist until the turn ends.

    `position` comes from the loop rather than the caller — several calls in one round
    are dispatched in the same millisecond, so a timestamp cannot order them and the
    caller should not have to think about it.
    """
    written: list[ToolCall] = []
    position_in_round: dict[int, int] = {}
    for call in calls:
        position = position_in_round.get(call.round_index, 0)
        position_in_round[call.round_index] = position + 1
        row = await fetch_one(
            conn,
            _INSERT_TOOL_CALL,
            session_id,
            message_id,
            call.round_index,
            position,
            call.name,
            json.dumps(call.arguments),
            call.outcome,
            call.text,
            call.duration_ms,
        )
        written.append(_tool_call_from_row(row))
    return written


async def get_tool_calls(conn: Conn, *, message_id: int) -> list[ToolCall]:
    rows = await conn.fetch(_SELECT_TOOL_CALLS, message_id)
    return [_tool_call_from_row(row) for row in rows]


async def get_session_tool_calls(conn: Conn, *, session_id: int) -> dict[int, list[ToolCall]]:
    """Every call in a session, grouped by the message it belongs to.

    One query, not one per message: the transcript route reads a whole session at once,
    and a rozmowa of forty exchanges would otherwise cost forty round trips to answer a
    single request. Messages with no calls are simply absent from the mapping — the
    caller reads it with a default, so an empty list never has to be stored.
    """
    rows = await conn.fetch(_SELECT_SESSION_TOOL_CALLS, session_id)
    grouped: dict[int, list[ToolCall]] = {}
    for row in rows:
        call = _tool_call_from_row(row)
        grouped.setdefault(call.message_id, []).append(call)
    return grouped


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


# --- prompt (specs/agent-prompt-management, "Zapis tworzy nową wersję, nigdy nie
# nadpisuje istniejącej") — global to the module, not scoped to an owner: one prompt,
# not one per operator.

_SELECT_LATEST_PROMPT_REVISION = """
    SELECT version, with_tools_body, without_tools_body, created_at
      FROM prompt_revisions
     ORDER BY id DESC
     LIMIT 1
"""

_INSERT_PROMPT_REVISION = """
    INSERT INTO prompt_revisions (version, with_tools_body, without_tools_body)
    VALUES ($1, $2, $3)
    RETURNING version, with_tools_body, without_tools_body, created_at
"""


def _prompt_revision_from_row(row: asyncpg.Record) -> PromptRevision:
    return PromptRevision(**dict(row))


def _next_prompt_version(current: str) -> str:
    """`"v4"` -> `"v5"` — the migration seeds the first row `"v4"`, matching the last
    version the code-constant scheme used, so this only ever has to add one."""
    return f"v{int(current.removeprefix('v')) + 1}"


async def latest_prompt_revision(conn: Conn) -> PromptRevision:
    row = await fetch_one(conn, _SELECT_LATEST_PROMPT_REVISION)
    return _prompt_revision_from_row(row)


async def create_prompt_revision(
    conn: Conn, *, with_tools_body: str, without_tools_body: str
) -> PromptRevision:
    """Always a new row — an edit is never applied to the one it replaces, the same
    append-only shape as `tool_calls`. Blank text is refused at the contract layer
    (`PromptUpdateIn`), not here; this function trusts what it is given."""
    async with conn.transaction():
        current = await fetch_one(conn, _SELECT_LATEST_PROMPT_REVISION)
        next_version = _next_prompt_version(current["version"])
        row = await fetch_one(
            conn, _INSERT_PROMPT_REVISION, next_version, with_tools_body, without_tools_body
        )
    return _prompt_revision_from_row(row)
