"""Runs one turn: calls the graph, forwards its deltas to a queue, and writes exactly one agent message
plus one usage row — always, whether the call finished, failed, or the listener went away first.

The queue is unbounded, so `put_nowait` never blocks and a turn never stalls on a consumer that stopped
reading. That is the whole mechanism behind a disconnect closing the queue rather than the turn."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import partial
from typing import Protocol

import asyncpg

from . import store
from .graph import LocalTool, StopSignal, build_graph, initial_state
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
    """One resolved tool call, on its way to whoever is listening. Carries the same call the database row
    is built from — the panel and the transcript must not disagree about what was asked."""

    call: RecordedCall
    position: int


@dataclass(frozen=True)
class Complete:
    incomplete: bool


@dataclass(frozen=True)
class Failed:
    message: str


@dataclass(frozen=True)
class Stopped:
    """The operator ended this turn. A third ending rather than a flavour of either of the two above: a
    turn that broke is something to try again, and a turn that was stopped is not."""


StreamEvent = Fragment | ToolCalled | Complete | Failed | Stopped


class Queue(Protocol):
    """The one method this module needs from `asyncio.Queue` — a `Protocol` so a test can hand in something
    that also doesn't drain. Positional-only, because the real parameter is named `item`, not `event`."""

    def put_nowait(self, event: StreamEvent, /) -> None: ...


def _system_prompt(revision, *, has_tools: bool, chart: ChartSnapshot | None) -> str:
    """The revision's own text, plus one line about what the caller is looking at. Appended to the system
    prompt rather than pushed into the transcript, so it describes this turn only."""
    body = prompt_text(revision, has_tools=has_tools)
    if chart is None:
        return body
    return body + "\n\n" + chart.as_context()


class _PoolAccountTrace:
    """The two halves of a tool call's own row: written before the call goes out, settled when its answer
    comes back. Its own connection per half — a turn spends most of its time waiting on a model."""

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
    operator_principal: str | None = None,
    stop: StopSignal | None = None,
) -> None:
    async with pool.acquire() as conn:
        messages = await store.get_messages(conn, session_id=session_id)
        revision = await store.latest_prompt_revision(conn)
    history = [(m.role.value, m.content) for m in messages]

    async def on_delta(text: str) -> None:
        queue.put_nowait(Fragment(text))

    async def on_tool_call(call: RecordedCall, position: int) -> None:
        queue.put_nowait(ToolCalled(call, position))

    # Asked here rather than inside the graph, so a turn's tool set is fixed before the first model call:
    # a list that changed between rounds would leave the provider holding a call for a tool that had gone.
    server_tools = (
        await tool_server.list_tools(operator_principal) if tool_server is not None else []
    )

    # This module's own tools sit beside the server's and are announced even when the server is down —
    # they need it to check against, not to exist, and they say so themselves when they cannot.
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
        provider, tool_server, local_tools, operator_principal, _PoolAccountTrace(pool, session_id)
    )
    try:
        result = await graph.ainvoke(
            initial_state(
                # Which prompt this turn runs is a fact about the turn, not a change to the prompt.
                # Measured against `server_tools`: the chart tool is always there, and would hide the archive.
                system_prompt=_system_prompt(revision, has_tools=bool(server_tools), chart=chart),
                history=history,
                model=model_entry.model,
                on_delta=on_delta,
                on_tool_call=on_tool_call,
                tools=tools,
                stop=stop,
            )
        )
        text: str = result["text"]
        usages = result["usages"]
        calls = result["calls"]
        failed: bool = result["failed"]
        stopped: bool = result["stopped"]
    except Exception:
        # A last-resort backstop, not the primary path: the graph's own node already catches a broken
        # provider call. Reaching here means the graph wiring itself failed.
        log.exception("the conversation graph failed for session %s", session_id)
        text, usages, calls, failed, stopped = "", [None], [], True, False

    async with pool.acquire() as conn:
        reply = await store.append_agent_message(
            conn,
            session_id=session_id,
            content=text,
            model_id=model_entry.id,
            prompt_version=revision.version,
            # A stopped reply is not the whole answer either — `incomplete` says that much. `stopped` is
            # the half `incomplete` cannot carry: who ended it.
            incomplete=failed or stopped,
            stopped=stopped,
        )
        # One row per model call, all pointing at this one reply. A turn that asked for a tool was billed
        # at least twice, and the tool's answer went into the prompt of the call after it.
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
        # Two halves, because a turn can hold both kinds: the calls whose rows were written before they
        # were sent are only joined to this reply, and everything else is inserted here.
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
    elif stopped:
        queue.put_nowait(Stopped())
    else:
        queue.put_nowait(Complete(incomplete=False))
