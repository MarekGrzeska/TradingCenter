"""Two nodes and a loop between them: the model call, and the tools it asks for.

History is rebuilt from the database on every turn — the graph itself carries no memory
(add-agent-chat/design.md, "Własne tabele są prawdą, LangGraph nie trzyma transkryptu").
Tool rounds live in the state for the length of one turn and are not replayed into the
next (connect-agent-to-market-mcp/design.md, "Wynik narzędzia żyje jedną turę").

Three failures are kept apart here, and conflating any two of them is the mistake this
file exists to avoid:

- the **tool** refused — market-mcp answered, and its answer names what to change. Back
  to the model, which can act on it.
- the tool **server** could not be reached — nothing was asked, so nothing is known
  about the archive either way. Also back to the model, worded so it does not read as
  missing data.
- the **provider** broke — nothing more will be generated. The turn ends with whatever
  text arrived, marked incomplete.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from .provider import (
    ModelProvider,
    TextDelta,
    ToolCallRequest,
    ToolCallResult,
    ToolRound,
    UsageReport,
)
from .tools import ToolDescriptor, ToolOutcomeKind, ToolServer

# A number in the code, not a setting — the same choice market-mcp made for its own
# ceilings, and for the same reason: a safety ceiling in configuration is an invitation
# to raise it at the moment it is inconvenient. Eight, because a real analytical turn is
# coverage, candles, indicators and levels — four or five calls — and eight leaves room
# while still bounding a runaway loop to a known multiple of one turn's cost.
TOOL_CALL_CEILING = 8


@dataclass(frozen=True)
class RecordedCall:
    """What group 3 writes to the database. Built here because this is the only place
    that knows the round number and what the call actually cost in time."""

    round_index: int
    name: str
    arguments: dict[str, Any]
    outcome: str
    text: str
    duration_ms: int


class ConversationState(TypedDict):
    system_prompt: str
    # (role, content) pairs, oldest first, this module's own vocabulary
    # ("operator"/"agent") — never langchain's message classes.
    history: list[tuple[str, str]]
    model: str
    # Called with each fragment of text as it arrives. Not persisted or checkpointed —
    # there is none (design.md) — so a plain closure is safe to carry in state.
    on_delta: Callable[[str], Awaitable[None]]
    tools: list[ToolDescriptor]
    rounds: list[ToolRound]
    calls: list[RecordedCall]
    # One per model call, in order. A turn with tools has more than one, and every one
    # of them is billed (specs/agent-usage, "Tura z wywołaniem narzędzia").
    usages: list[UsageReport | None]
    pending: list[ToolCallRequest]
    tool_calls_made: int
    text: str
    failed: bool


def build_graph(provider: ModelProvider, tool_server: ToolServer | None = None):
    async def call_model(state: ConversationState) -> dict:
        parts: list[str] = []
        requests: list[ToolCallRequest] = []
        usage: UsageReport | None = None
        # Past the ceiling the model is called with no tools at all, rather than with
        # tools it is told not to use. A model holding a tool it may not call is being
        # asked to obey a rule; a model holding none is simply answering
        # (specs/agent-tools, "Tura ma sufit wywołań narzędzi").
        offered = state["tools"] if state["tool_calls_made"] < TOOL_CALL_CEILING else []
        try:
            async for chunk in provider.stream(
                model=state["model"],
                system_prompt=state["system_prompt"],
                history=state["history"],
                tools=offered,
                rounds=state["rounds"],
            ):
                if isinstance(chunk, TextDelta):
                    parts.append(chunk.text)
                    await state["on_delta"](chunk.text)
                elif isinstance(chunk, ToolCallRequest):
                    requests.append(chunk)
                else:
                    usage = chunk
        except Exception:  # noqa: BLE001 - any provider failure must still return partial text
            # Caught here, not by the caller: whatever text arrived before the
            # provider broke must still be returned, not lost along with the
            # exception (specs/agent-chat, "Model przerywa w połowie").
            return {
                "text": state["text"] + "".join(parts),
                "usages": [*state["usages"], usage],
                "pending": [],
                "failed": True,
            }
        return {
            "text": state["text"] + "".join(parts),
            "usages": [*state["usages"], usage],
            "pending": requests,
            "failed": False,
        }

    async def run_tools(state: ConversationState) -> dict:
        round_index = len(state["rounds"])
        made = state["tool_calls_made"]
        results: list[ToolCallResult] = []
        recorded: list[RecordedCall] = []

        for request in state["pending"]:
            if made >= TOOL_CALL_CEILING:
                # Not executed, so not recorded as a call — nothing was asked of the
                # server. The model still gets a result for its request, because a
                # request left unanswered is a turn that never ends.
                results.append(
                    ToolCallResult(
                        id=request.id,
                        name=request.name,
                        text=(
                            f"not called: this turn has already made {TOOL_CALL_CEILING} "
                            "tool calls, which is the limit. Answer the operator with "
                            "what you have, and say what you could not check."
                        ),
                    )
                )
                continue

            outcome = await tool_server.call(request.name, request.arguments) if tool_server else None
            made += 1
            if outcome is None:  # pragma: no cover - a graph built without a server
                text, kind = "no tool server is available", ToolOutcomeKind.UNAVAILABLE
                duration = 0
            else:
                text, kind, duration = outcome.text, outcome.kind, outcome.duration_ms
            results.append(ToolCallResult(id=request.id, name=request.name, text=text))
            recorded.append(
                RecordedCall(
                    round_index=round_index,
                    name=request.name,
                    arguments=request.arguments,
                    outcome=str(kind),
                    text=text,
                    duration_ms=duration,
                )
            )

        return {
            "rounds": [*state["rounds"], ToolRound(tuple(state["pending"]), tuple(results))],
            "calls": [*state["calls"], *recorded],
            "tool_calls_made": made,
            "pending": [],
        }

    def after_model(state: ConversationState) -> str:
        if state["failed"] or not state["pending"]:
            return END
        return "tools"

    graph = StateGraph(ConversationState)
    graph.add_node("model", call_model)
    graph.add_node("tools", run_tools)
    graph.set_entry_point("model")
    graph.add_conditional_edges("model", after_model, {"tools": "tools", END: END})
    graph.add_edge("tools", "model")
    return graph.compile()


def initial_state(
    *,
    system_prompt: str,
    history: list[tuple[str, str]],
    model: str,
    on_delta: Callable[[str], Awaitable[None]],
    tools: Sequence[ToolDescriptor] = (),
) -> ConversationState:
    return {
        "system_prompt": system_prompt,
        "history": history,
        "model": model,
        "on_delta": on_delta,
        "tools": list(tools),
        "rounds": [],
        "calls": [],
        "usages": [],
        "pending": [],
        "tool_calls_made": 0,
        "text": "",
        "failed": False,
    }
