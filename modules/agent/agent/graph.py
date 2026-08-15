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

import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import TypedDict

from langgraph.graph import END, StateGraph

from .models import RecordedCall
from .provider import (
    ModelProvider,
    TextDelta,
    ToolCallRequest,
    ToolCallResult,
    ToolRound,
    UsageReport,
)
from .tools import ToolDescriptor, ToolOutcome, ToolOutcomeKind, ToolServer

log = logging.getLogger(__name__)

# A tool this module runs itself, already bound to whatever it needs beyond the model's
# arguments (the session, the pool). The graph does not care which tools are local — it
# looks a name up here first and falls through to the server — so the ceiling, the trace
# and the three outcomes stay one mechanism for both kinds (specs/agent-tools, "Zestaw
# narzędzi pochodzi z serwera, nie z tego modułu").
LocalTool = Callable[[dict], Awaitable[ToolOutcome]]

# A number in the code, not a setting — the same choice market-mcp made for its own
# ceilings, and for the same reason: a safety ceiling in configuration is an invitation
# to raise it at the moment it is inconvenient. Eight, because a real analytical turn is
# coverage, candles, indicators and levels — four or five calls — and eight leaves room
# while still bounding a runaway loop to a known multiple of one turn's cost.
#
# Raising it past about ten needs a second edit, in a place nothing points at from here:
# a turn of N rounds costs 2N+1 supersteps and LangGraph's default `recursion_limit` is
# 25, so the graph would stop with its own error before this ceiling ever spoke. At
# eight that is 17, with room to spare.
TOOL_CALL_CEILING = 8


class ConversationState(TypedDict):
    system_prompt: str
    # (role, content) pairs, oldest first, this module's own vocabulary
    # ("operator"/"agent") — never langchain's message classes.
    history: list[tuple[str, str]]
    model: str
    # Called with each fragment of text as it arrives. Not persisted or checkpointed —
    # there is none (design.md) — so a plain closure is safe to carry in state.
    on_delta: Callable[[str], Awaitable[None]]
    # The same idea for a tool call, called once the call has resolved. A round of tools
    # produces no text, so without this the caller sees nothing between the model's last
    # fragment and its next one — and cannot tell a turn reading the archive from a turn
    # that hung (specs/agent-chat, "Wywołanie narzędzia dociera w trakcie tury").
    # Takes the call and its position within its round: `store.record_tool_calls` derives
    # the same number from its own loop, and the two must agree or the panel and the
    # reloaded transcript order a round differently.
    on_tool_call: Callable[[RecordedCall, int], Awaitable[None]]
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


def build_graph(
    provider: ModelProvider,
    tool_server: ToolServer | None = None,
    local_tools: Mapping[str, LocalTool] | None = None,
):
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
        except Exception:
            # Caught here, not by the caller: whatever text arrived before the
            # provider broke must still be returned, not lost along with the
            # exception (specs/agent-chat, "Model przerywa w połowie").
            #
            # Logged with the traceback before it is turned into a flag. Without this
            # line the operator sees "incomplete — broke off" in the panel and there is
            # no record anywhere of what broke: the exception dies here, and `turn.py`'s
            # own backstop never runs because nothing propagates. Measured the hard way.
            log.exception(
                "the model call failed after %d tool call(s), %d tool(s) offered",
                state["tool_calls_made"],
                len(offered),
            )
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
                # Not executed, so neither recorded nor announced — nothing was asked of
                # the server, and an event here would put a call in the operator's panel
                # that never happened. The model still gets a result for its request,
                # because a request left unanswered is a turn that never ends.
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

            local = (local_tools or {}).get(request.name)
            if local is not None:
                try:
                    outcome = await local(request.arguments)
                except Exception as err:  # noqa: BLE001 - a broken local tool is not a broken turn
                    # Mirrors `ToolServer.call`'s own guard: this module's own tool can fail
                    # (a database gone away, a malformed row) exactly as a remote one can,
                    # and without this the exception reaches `turn.py`'s backstop, which
                    # discards the whole turn's text rather than reporting one failed call.
                    log.warning("local tool %s failed: %s", request.name, err)
                    outcome = ToolOutcome(
                        ToolOutcomeKind.UNAVAILABLE,
                        f"this tool failed unexpectedly ({err}). Nothing was changed.",
                        0,
                    )
            elif tool_server is not None:
                outcome = await tool_server.call(request.name, request.arguments)
            else:
                outcome = None
            made += 1
            if outcome is None:  # pragma: no cover - a graph built without a server
                text, kind = "no tool server is available", ToolOutcomeKind.UNAVAILABLE
                duration = 0
            else:
                text, kind, duration = outcome.text, outcome.kind, outcome.duration_ms
            results.append(ToolCallResult(id=request.id, name=request.name, text=text))
            call = RecordedCall(
                round_index=round_index,
                name=request.name,
                arguments=request.arguments,
                outcome=str(kind),
                text=text,
                duration_ms=duration,
            )
            recorded.append(call)
            # Announced before the loop moves on, so a round of three calls reaches the
            # caller as three events in the order they resolved — not as three at once
            # when the round ends. `recorded` holds this round alone, so its length is
            # the position the store will write for the same call.
            await state["on_tool_call"](call, len(recorded) - 1)

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
    on_tool_call: Callable[[RecordedCall, int], Awaitable[None]],
    tools: Sequence[ToolDescriptor] = (),
) -> ConversationState:
    return {
        "system_prompt": system_prompt,
        "history": history,
        "model": model,
        "on_delta": on_delta,
        "on_tool_call": on_tool_call,
        "tools": list(tools),
        "rounds": [],
        "calls": [],
        "usages": [],
        "pending": [],
        "tool_calls_made": 0,
        "text": "",
        "failed": False,
    }
