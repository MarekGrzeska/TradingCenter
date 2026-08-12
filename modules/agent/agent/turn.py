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
from typing import Protocol

import asyncpg

from . import store
from .graph import build_graph, initial_state
from .models_catalogue import ModelCatalogueEntry
from .prompt import PROMPT_VERSION, system_prompt
from .provider import ModelProvider
from .tools import ToolServer

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Fragment:
    text: str


@dataclass(frozen=True)
class Complete:
    incomplete: bool


@dataclass(frozen=True)
class Failed:
    message: str


StreamEvent = Fragment | Complete | Failed


class Queue(Protocol):
    """The one method this module needs from `asyncio.Queue` — a `Protocol` so a test
    can hand in something that also *doesn't* drain, without importing asyncio's type.

    Positional-only (`/`): `asyncio.Queue.put_nowait`'s own parameter is named `item`,
    not `event`, and a name mismatch on a keyword-usable parameter is a structural
    mismatch to a type checker even though nothing here ever calls it by keyword.
    """

    def put_nowait(self, event: StreamEvent, /) -> None: ...


async def run_turn(
    pool: asyncpg.Pool,
    *,
    session_id: int,
    model_entry: ModelCatalogueEntry,
    provider: ModelProvider,
    queue: Queue,
    tool_server: ToolServer | None = None,
) -> None:
    async with pool.acquire() as conn:
        messages = await store.get_messages(conn, session_id=session_id)
    history = [(m.role.value, m.content) for m in messages]

    async def on_delta(text: str) -> None:
        queue.put_nowait(Fragment(text))

    # Asked here rather than inside the graph so a turn's tool set is fixed before the
    # first model call: a list that changed between rounds would leave the provider
    # holding a call for a tool that had just gone away. An empty list is the whole
    # answer to a tool server that is down (specs/agent-tool-access).
    tools = await tool_server.list_tools() if tool_server is not None else []

    graph = build_graph(provider, tool_server)
    try:
        result = await graph.ainvoke(
            initial_state(
                # Which prompt this turn runs is a fact about the turn, not a change to
                # the prompt: both texts are `v3`, and the one without tools is what an
                # unreachable market-mcp degrades to (specs/agent-chat, "Agent bez
                # narzędzi mówi, że ich nie ma").
                system_prompt=system_prompt(has_tools=bool(tools)),
                history=history,
                model=model_entry.model,
                on_delta=on_delta,
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
            prompt_version=PROMPT_VERSION,
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
        await store.record_tool_calls(
            conn, session_id=session_id, message_id=reply.id, calls=calls
        )

    if failed:
        queue.put_nowait(Failed("the model call failed"))
    else:
        queue.put_nowait(Complete(incomplete=False))
