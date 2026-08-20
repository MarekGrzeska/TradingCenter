"""The transcript — one row per turn, operator's and agent's alike.

`_TOUCH_SESSION` lives here rather than with the sessions it writes to, because this is
the only place that fires it: appending the first operator message is what gives a
session its title and its place in the list.
"""

from __future__ import annotations

import asyncpg
from tc_runtime.db import Conn, fetch_one

from ..models import (
    Message,
    Role,
)
from .sessions import derive_title

_SELECT_MESSAGES = """
    SELECT id, session_id, role, content, model_id, prompt_version, incomplete, stopped,
           created_at
      FROM messages
     WHERE session_id = $1
     ORDER BY id
"""

_INSERT_MESSAGE = """
    INSERT INTO messages (session_id, role, content, model_id, prompt_version, incomplete,
                          stopped)
    VALUES ($1, $2, $3, $4, $5, $6, $7)
    RETURNING id, session_id, role, content, model_id, prompt_version, incomplete, stopped,
              created_at
"""

_TOUCH_SESSION = """
    UPDATE sessions SET last_active_at = now(), title = COALESCE(title, $2)
     WHERE id = $1
"""

def _message_from_row(row: asyncpg.Record) -> Message:
    data = dict(row)
    data["role"] = Role(data["role"])
    return Message(**data)

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
            conn,
            _INSERT_MESSAGE,
            session_id,
            Role.OPERATOR.value,
            content,
            None,
            None,
            False,
            False,
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
    stopped: bool = False,
) -> Message:
    """One row, however the turn ended. `stopped` is the operator's own ending — always
    alongside `incomplete`, never instead of it: a stopped reply is not the whole answer
    either, and a reader filtering on `incomplete` MUST NOT stop seeing it."""
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
            stopped,
        )
        await conn.execute("UPDATE sessions SET last_active_at = now() WHERE id = $1", session_id)
    return _message_from_row(row)
