"""Reading and writing everything this module owns — the only door to its tables.

Same shape as `market_data/store.py`: asyncpg directly, no ORM in the runtime path. One
module per table, because that is the only seam that held when the single 911-line file
was read for one: each table's SQL, its row mapper and its functions belong together and
to nothing else.

The names below are the whole public surface and every caller reaches them the same way
it always did — `from .. import store`, then `store.create_session(...)`. Nothing outside
this package imports a submodule directly, and nothing needs to.

The split fixed one real defect rather than only shortening files: `usage` was written in
one place and aggregated 250 lines further down, with the whole tool-call section between
the two halves of one table.
"""

from __future__ import annotations

from .chart_commands import chart_state_after, record_chart_command
from .drawings import (
    MAX_DRAWING_ID,
    MAX_DRAWINGS_PER_SYMBOL,
    add_drawings,
    count_drawings,
    delete_drawing,
    list_drawings,
    lock_drawing,
    remove_drawings,
    set_drawings_hidden,
    update_drawing,
)
from .messages import append_agent_message, append_operator_message, get_messages
from .prompt import create_prompt_revision, latest_prompt_revision
from .sessions import (
    create_session,
    delete_session,
    derive_title,
    get_session,
    list_sessions,
    set_session_model,
    set_session_title,
)
from .tool_calls import (
    attach_tool_calls_to_message,
    begin_tool_call,
    get_session_orphan_tool_calls,
    get_session_tool_calls,
    get_tool_calls,
    record_tool_calls,
    settle_tool_call,
)
from .usage import (
    record_usage,
    usage_by_day,
    usage_by_model,
    usage_by_session,
    usage_total_cost,
)

__all__ = [
    "MAX_DRAWINGS_PER_SYMBOL",
    "MAX_DRAWING_ID",
    "add_drawings",
    "append_agent_message",
    "append_operator_message",
    "attach_tool_calls_to_message",
    "begin_tool_call",
    "chart_state_after",
    "count_drawings",
    "create_prompt_revision",
    "create_session",
    "delete_drawing",
    "delete_session",
    "derive_title",
    "get_messages",
    "get_session",
    "get_session_orphan_tool_calls",
    "get_session_tool_calls",
    "get_tool_calls",
    "latest_prompt_revision",
    "list_drawings",
    "list_sessions",
    "lock_drawing",
    "record_chart_command",
    "record_tool_calls",
    "record_usage",
    "remove_drawings",
    "set_drawings_hidden",
    "set_session_model",
    "set_session_title",
    "settle_tool_call",
    "update_drawing",
    "usage_by_day",
    "usage_by_model",
    "usage_by_session",
    "usage_total_cost",
]
