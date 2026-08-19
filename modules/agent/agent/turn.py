"""Runs one turn: calls the graph, forwards its deltas to a queue, and writes exactly
one agent message plus one usage row — always, whether the call finished, failed, or
whoever was listening to the queue went away first.

The queue is `asyncio.Queue`, unbounded by default: `put_nowait` never blocks, so a
turn this function drives never stalls on a consumer that stopped reading. That is the
whole mechanism behind "a rozłączenie wołającego zamyka kolejkę, nie turę" — there is no
cancellation to wire up, because nothing here depends on the queue being drained.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import partial
from typing import Protocol

import asyncpg

from . import store
from .graph import LocalTool, build_graph, initial_state
from .models import ChartSnapshot, RecordedCall
from .models_catalogue import ModelCatalogueEntry
from .prompt import prompt_text
from .provider import ModelProvider
from .tools import (
    CHART_TOOL,
    CHART_TOOL_NAME,
    DRAW_TOOL,
    DRAW_TOOL_NAME,
    LIST_DRAWINGS_TOOL,
    LIST_DRAWINGS_TOOL_NAME,
    ChartTool,
    DrawOnChartTool,
    ListChartDrawingsTool,
    ToolServer,
)

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Fragment:
    text: str


@dataclass(frozen=True)
class ToolCalled:
    """One resolved tool call, on its way to whoever is listening to this turn. Carries
    the same call the database row is built from — the panel and the transcript must not
    be able to disagree about what was asked and what came back."""

    call: RecordedCall
    position: int


@dataclass(frozen=True)
class Complete:
    incomplete: bool


@dataclass(frozen=True)
class Failed:
    message: str


StreamEvent = Fragment | ToolCalled | Complete | Failed


class Queue(Protocol):
    """The one method this module needs from `asyncio.Queue` — a `Protocol` so a test
    can hand in something that also *doesn't* drain, without importing asyncio's type.

    Positional-only (`/`): `asyncio.Queue.put_nowait`'s own parameter is named `item`,
    not `event`, and a name mismatch on a keyword-usable parameter is a structural
    mismatch to a type checker even though nothing here ever calls it by keyword.
    """

    def put_nowait(self, event: StreamEvent, /) -> None: ...


def _system_prompt(revision, *, has_tools: bool, chart: ChartSnapshot | None) -> str:
    """The revision's own text, plus one line about what the caller is looking at.

    Appended to the system prompt rather than pushed into the transcript: the transcript
    is the conversation, and what was on screen when a question was asked is not part of
    it (specs/agent-chat, "Tura wie, co terminal właśnie rysuje"). It also means the line
    describes *this* turn only — the next one brings its own, or none.
    """
    body = prompt_text(revision, has_tools=has_tools)
    if chart is None:
        return body
    return body + "\n\n" + chart.as_context()


class _PoolAccountTrace:
    """The two halves of a tool call's own row: written before the call goes out, settled
    when its answer comes back (design.md, D1).

    Its own connection per half, not one held for the turn: a turn spends most of its
    time waiting on a model, and a pooled connection parked across that is a connection
    nobody else can have. Both halves are short.
    """

    def __init__(self, pool: asyncpg.Pool, session_id: int) -> None:
        self._pool = pool
        self._session_id = session_id

    async def begin(self, *, round_index: int, position: int, name: str, arguments: dict) -> int:
        async with self._pool.acquire() as conn:
            return await store.begin_tool_call(
                conn,
                session_id=self._session_id,
                round_index=round_index,
                position=position,
                tool_name=name,
                arguments=arguments,
                result_text=(
                    "sent; no answer had come back when this was written. If it stays "
                    "this way, the outcome of this call is unknown."
                ),
            )

    async def settle(self, *, row_id: int, outcome: str, text: str, duration_ms: int) -> None:
        async with self._pool.acquire() as conn:
            await store.settle_tool_call(
                conn,
                tool_call_id=row_id,
                outcome=outcome,
                result_text=text,
                duration_ms=duration_ms,
            )


async def run_turn(
    pool: asyncpg.Pool,
    *,
    session_id: int,
    model_entry: ModelCatalogueEntry,
    provider: ModelProvider,
    queue: Queue,
    tool_server: ToolServer | None = None,
    chart: ChartSnapshot | None = None,
    operator_token: str | None = None,
) -> None:
    async with pool.acquire() as conn:
        messages = await store.get_messages(conn, session_id=session_id)
        revision = await store.latest_prompt_revision(conn)
    history = [(m.role.value, m.content) for m in messages]

    async def on_delta(text: str) -> None:
        queue.put_nowait(Fragment(text))

    async def on_tool_call(call: RecordedCall, position: int) -> None:
        queue.put_nowait(ToolCalled(call, position))

    # Asked here rather than inside the graph so a turn's tool set is fixed before the
    # first model call: a list that changed between rounds would leave the provider
    # holding a call for a tool that had just gone away. An empty list is the whole
    # answer to a tool server that is down (specs/agent-tool-access).
    server_tools = (
        await tool_server.list_tools(operator_token) if tool_server is not None else []
    )

    # This module's own tools sit beside the server's and are announced even when the
    # server is down — they do not need market-mcp to exist, only to check against, and
    # they say so themselves when they cannot (specs/agent-tools, "Brak serwera
    # narzędzi"). `list_chart_drawings` does not even need that much: it reads this
    # module's own table and answers whatever the archive is doing.
    chart_tool = ChartTool(pool, tool_server)
    draw_tool = DrawOnChartTool(pool, tool_server)
    list_drawings_tool = ListChartDrawingsTool(pool)

    # Bound rather than wrapped: each of these took a three-line `async def` whose whole
    # body was the same call with this turn's session and chart filled in.
    local_tools: dict[str, LocalTool] = {
        CHART_TOOL_NAME: partial(chart_tool.call, session_id=session_id, chart=chart),
        DRAW_TOOL_NAME: partial(draw_tool.call, session_id=session_id),
        LIST_DRAWINGS_TOOL_NAME: list_drawings_tool.call,
    }
    tools = [*server_tools, CHART_TOOL, DRAW_TOOL, LIST_DRAWINGS_TOOL]

    graph = build_graph(
        provider, tool_server, local_tools, operator_token, _PoolAccountTrace(pool, session_id)
    )
    try:
        result = await graph.ainvoke(
            initial_state(
                # Which prompt this turn runs is a fact about the turn, not a change to
                # the prompt: `revision` was current when this turn started, and the
                # variant without tools is what an unreachable market-mcp degrades to
                # (specs/agent-chat, "Agent bez narzędzi mówi, że ich nie ma"). Measured
                # against `server_tools` rather than `tools`: the chart tool is always
                # there, and letting it stand for "has tools" would hide the archive
                # being down. Both prompt variants name it; only one promises the archive.
                system_prompt=_system_prompt(revision, has_tools=bool(server_tools), chart=chart),
                history=history,
                model=model_entry.model,
                on_delta=on_delta,
                on_tool_call=on_tool_call,
                tools=tools,
            )
        )
        text: str = result["text"]
        usages = result["usages"]
        calls = result["calls"]
        failed: bool = result["failed"]
    except Exception:
        # A last-resort backstop, not the primary path: `graph.py`'s own node already
        # catches a broken provider call so partial text survives it. Reaching here
        # means the graph wiring itself failed, and nothing was ever generated.
        log.exception("the conversation graph failed for session %s", session_id)
        text, usages, calls, failed = "", [None], [], True

    async with pool.acquire() as conn:
        reply = await store.append_agent_message(
            conn,
            session_id=session_id,
            content=text,
            model_id=model_entry.id,
            prompt_version=revision.version,
            incomplete=failed,
        )
        # One row per model call, all pointing at this one reply. A turn that asked for
        # a tool was billed at least twice, and the tool's own answer went into the
        # prompt of the call after it (specs/agent-usage, "Tura z wywołaniem
        # narzędzia").
        for usage in usages:
            await store.record_usage(
                conn,
                session_id=session_id,
                message_id=reply.id,
                model_id=model_entry.id,
                input_tokens=usage.input_tokens if usage else None,
                output_tokens=usage.output_tokens if usage else None,
                cached_tokens=usage.cached_tokens if usage else None,
                reasoning_tokens=usage.reasoning_tokens if usage else None,
                input_rate_per_1m=model_entry.input_rate_per_1m,
                output_rate_per_1m=model_entry.output_rate_per_1m,
            )
        # Two halves, because a turn can now hold both kinds: the calls whose rows were
        # written before they were sent are only joined to this reply, and everything else
        # is inserted here as it always was (design.md, D1).
        await store.attach_tool_calls_to_message(
            conn,
            tool_call_ids=[call.row_id for call in calls if call.row_id is not None],
            message_id=reply.id,
        )
        await store.record_tool_calls(
            conn, session_id=session_id, message_id=reply.id, calls=calls
        )

    if failed:
        queue.put_nowait(Failed("the model call failed"))
    else:
        queue.put_nowait(Complete(incomplete=False))
