"""One node: the model call. History is rebuilt from the database on every turn — the
graph itself carries no memory (design.md, "Własne tabele są prawdą, LangGraph nie
trzyma transkryptu"). Room is left here, not filled: a tool node is what a later change
adds, not a shape this one guesses at (design.md, Non-Goals — no tools yet).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypedDict

from langgraph.graph import END, StateGraph

from .provider import ModelProvider, TextDelta, UsageReport


class ConversationState(TypedDict):
    system_prompt: str
    # (role, content) pairs, oldest first, this module's own vocabulary
    # ("operator"/"agent") — never langchain's message classes.
    history: list[tuple[str, str]]
    deployment: str
    # Called with each fragment of text as it arrives. Not persisted or checkpointed —
    # there is none (design.md) — so a plain closure is safe to carry in state.
    on_delta: Callable[[str], Awaitable[None]]
    text: str
    usage: UsageReport | None
    failed: bool


def build_graph(provider: ModelProvider):
    async def call_model(state: ConversationState) -> dict:
        parts: list[str] = []
        usage: UsageReport | None = None
        try:
            async for chunk in provider.stream(
                deployment=state["deployment"],
                system_prompt=state["system_prompt"],
                history=state["history"],
            ):
                if isinstance(chunk, TextDelta):
                    parts.append(chunk.text)
                    await state["on_delta"](chunk.text)
                else:
                    usage = chunk
        except Exception:  # noqa: BLE001 - any provider failure must still return partial text
            # Caught here, not by the caller: whatever text arrived before the
            # provider broke must still be returned, not lost along with the
            # exception (specs/agent-chat, "Model przerywa w połowie").
            return {"text": "".join(parts), "usage": usage, "failed": True}
        return {"text": "".join(parts), "usage": usage, "failed": False}

    graph = StateGraph(ConversationState)
    graph.add_node("model", call_model)
    graph.set_entry_point("model")
    graph.add_edge("model", END)
    return graph.compile()
