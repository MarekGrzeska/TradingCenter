"""The trace a tool call leaves — specs/agent-tools, "Wywołanie narzędzia zostawia ślad"."""

from __future__ import annotations

import json
from collections.abc import Sequence

import asyncpg
from tc_runtime.db import Conn, fetch_one

from ..models import (
    RecordedCall,
    ToolCall,
)

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

# `message_id` leads the ordering so the grouping below builds each message's list in the order the turn
# made the calls, in one pass. A row whose `message_id` is still NULL comes back from its own query.
_SELECT_SESSION_TOOL_CALLS = f"""
    SELECT {_TOOL_CALL_COLUMNS}
      FROM tool_calls
     WHERE session_id = $1 AND message_id IS NOT NULL
     ORDER BY message_id, round_index, position, id
"""

# The calls that outlived their turn — sent, and never joined to a reply, because there was none. Ordered
# oldest first, by the only thing they have: when they were made.
_SELECT_SESSION_ORPHAN_TOOL_CALLS = f"""
    SELECT {_TOOL_CALL_COLUMNS}
      FROM tool_calls
     WHERE session_id = $1 AND message_id IS NULL
     ORDER BY id
"""

# Written before the call is sent: no message yet, no outcome yet, and a duration of zero
# that `settle_tool_call` replaces with the real one.
_BEGIN_TOOL_CALL = """
    INSERT INTO tool_calls (
        session_id, message_id, round_index, position,
        tool_name, arguments, outcome, result_text, duration_ms
    )
    VALUES ($1, NULL, $2, $3, $4, $5::jsonb, 'unknown', $6, 0)
    RETURNING id
"""

_SETTLE_TOOL_CALL = """
    UPDATE tool_calls
       SET outcome = $2, result_text = $3, duration_ms = $4
     WHERE id = $1
"""

# Only rows still waiting for one. A row already carrying a `message_id` is somebody
# else's, and `id = ANY($2)` on its own would happily move it.
_ATTACH_TOOL_CALLS = """
    UPDATE tool_calls
       SET message_id = $1
     WHERE id = ANY($2::bigint[]) AND message_id IS NULL
"""


def _tool_call_from_row(row: asyncpg.Record) -> ToolCall:
    data = dict(row)
    # asyncpg hands JSONB back as text unless a codec is registered; parsing here keeps
    # that decision in the one place that reads the column.
    data["arguments"] = json.loads(data["arguments"]) if isinstance(data["arguments"], str) else (
        data["arguments"]
    )
    return ToolCall(**data)


async def begin_tool_call(
    conn: Conn,
    *,
    session_id: int,
    round_index: int,
    position: int,
    tool_name: str,
    arguments: dict,
    result_text: str,
) -> int:
    """A row for a call that is about to be sent, and only for calls that can change the account: a read that vanished
    with its turn left nothing to reconcile. `position` is the caller's, since the row exists before the round ends."""
    row = await fetch_one(
        conn,
        _BEGIN_TOOL_CALL,
        session_id,
        round_index,
        position,
        tool_name,
        json.dumps(arguments),
        result_text,
    )
    return int(row["id"])


async def settle_tool_call(
    conn: Conn, *, tool_call_id: int, outcome: str, result_text: str, duration_ms: int
) -> None:
    """The second half of `begin_tool_call`: what came back, once it did. A call that never comes back is
    never settled, and the row keeps the `unknown` it was written with."""
    await conn.execute(_SETTLE_TOOL_CALL, tool_call_id, outcome, result_text, duration_ms)


async def attach_tool_calls_to_message(
    conn: Conn, *, tool_call_ids: Sequence[int], message_id: int
) -> None:
    """Joins rows written before the reply existed to the reply, once it does — which is what makes a
    pre-written row indistinguishable from one `record_tool_calls` wrote."""
    if not tool_call_ids:
        return
    await conn.execute(_ATTACH_TOOL_CALLS, message_id, list(tool_call_ids))


async def record_tool_calls(
    conn: Conn,
    *,
    session_id: int,
    message_id: int,
    calls: Sequence[RecordedCall],
) -> list[ToolCall]:
    """Written after the agent message exists, because the id they hang off does not exist until the turn
    ends. `position` comes from the loop: several calls in one round are dispatched in the same millisecond."""
    written: list[ToolCall] = []
    position_in_round: dict[int, int] = {}
    for call in calls:
        position = position_in_round.get(call.round_index, 0)
        position_in_round[call.round_index] = position + 1
        if call.row_id is not None:
            continue
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
    """Every call in a session, grouped by the message it belongs to. One query, not one per message: a
    rozmowa of forty exchanges would otherwise cost forty round trips to answer one request."""
    rows = await conn.fetch(_SELECT_SESSION_TOOL_CALLS, session_id)
    grouped: dict[int, list[ToolCall]] = {}
    for row in rows:
        call = _tool_call_from_row(row)
        assert call.message_id is not None  # the query excludes NULLs
        grouped.setdefault(call.message_id, []).append(call)
    return grouped


async def get_session_orphan_tool_calls(conn: Conn, *, session_id: int) -> list[ToolCall]:
    """The calls in this session that no reply ever claimed. Read separately because there is no message to
    fold them under — and dropping them would hide the one row this mechanism exists to keep."""
    rows = await conn.fetch(_SELECT_SESSION_ORPHAN_TOOL_CALLS, session_id)
    return [_tool_call_from_row(row) for row in rows]
