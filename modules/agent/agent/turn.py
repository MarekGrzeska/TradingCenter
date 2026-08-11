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
from .graph import build_graph
from .models_catalogue import ModelCatalogueEntry
from .prompt import PROMPT_VERSION, SYSTEM_PROMPT
from .provider import ModelProvider

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
) -> None:
    async with pool.acquire() as conn:
        messages = await store.get_messages(conn, session_id=session_id)
    history = [(m.role.value, m.content) for m in messages]

    async def on_delta(text: str) -> None:
        queue.put_nowait(Fragment(text))

    graph = build_graph(provider)
    try:
        result = await graph.ainvoke(
            {
                "system_prompt": SYSTEM_PROMPT,
                "history": history,
                "deployment": model_entry.deployment,
                "on_delta": on_delta,
                "text": "",
                "usage": None,
                "failed": False,
            }
        )
        text: str = result["text"]
        usage = result["usage"]
        failed: bool = result["failed"]
    except Exception:
        # A last-resort backstop, not the primary path: `graph.py`'s own node already
        # catches a broken provider call so partial text survives it. Reaching here
        # means the graph wiring itself failed, and nothing was ever generated.
        log.exception("the conversation graph failed for session %s", session_id)
        text, usage, failed = "", None, True

    async with pool.acquire() as conn:
        reply = await store.append_agent_message(
            conn,
            session_id=session_id,
            content=text,
            model_id=model_entry.id,
            prompt_version=PROMPT_VERSION,
            incomplete=failed,
        )
        await store.record_usage(
            conn,
            session_id=session_id,
            message_id=reply.id,
            model_id=model_entry.id,
            input_tokens=usage.input_tokens if usage else None,
            output_tokens=usage.output_tokens if usage else None,
            cached_tokens=usage.cached_tokens if usage else None,
            reasoning_tokens=usage.reasoning_tokens if usage else None,
            input_rate_per_1k=model_entry.input_rate_per_1k,
            output_rate_per_1k=model_entry.output_rate_per_1k,
        )

    if failed:
        queue.put_nowait(Failed("the model call failed"))
    else:
        queue.put_nowait(Complete(incomplete=False))
