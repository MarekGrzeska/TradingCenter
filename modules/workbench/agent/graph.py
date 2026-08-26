"""Two nodes and a loop between them: the model call, and the tools it asks for. History is rebuilt from
the database on every turn, and tool rounds live in the state for one turn only.

Four failures are kept apart, and conflating any two is the mistake this file exists to avoid: the tool
refused, the server could not be reached, the server could not be reached *and the call could have
landed* — the one the model must not retry on — and the provider broke mid-answer."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Protocol, TypedDict

from langgraph.graph import END, StateGraph

from .models import RecordedCall
from .provider import (
    Conversation,
    ModelProvider,
    TextDelta,
    ToolCallRequest,
    ToolCallResult,
    ToolRound,
    UsageReport,
)
from .tools import ToolDescriptor, ToolOutcome, ToolOutcomeKind, ToolServer

log = logging.getLogger(__name__)

# A tool this module runs itself, already bound to whatever it needs beyond the model's arguments. The
# graph looks a name up here first and falls through to the server, so the trace stays one mechanism.
LocalTool = Callable[[dict], Awaitable[ToolOutcome]]


class StopSignal(Protocol):
    """Whether the operator has asked for this turn to end. `asyncio.Event` satisfies it; who sets it and
    how it travelled from a route to here is `routers/sessions.py`'s business."""

    def is_set(self) -> bool: ...


class AccountTrace(Protocol):
    """The two halves of the trace a call that can move the account leaves: a row before it is sent, and
    its outcome once one is known. A call never settled keeps the `unknown` it was begun with."""

    async def begin(
        self, *, round_index: int, position: int, name: str, arguments: dict
    ) -> int: ...

    async def settle(
        self, *, row_id: int, outcome: str, text: str, duration_ms: int
    ) -> None: ...

# A number in the code, not a setting: a safety ceiling in configuration is an invitation to raise it at
# the moment it is inconvenient. Past about ten a second edit is needed — LangGraph's own recursion limit.
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
    # The same idea for a tool call, called once it has resolved: a round of tools produces no text, and
    # without this the caller cannot tell a turn reading the archive from a turn that hung.
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
    # Asked between one fragment and the next, and once more before a round of tools turns into another
    # model call. Never inside `run_tools`: a call that has been sent is finished and recorded.
    stop: StopSignal | None
    stopped: bool


def build_graph(
    provider: ModelProvider,
    tool_server: ToolServer | None = None,
    local_tools: Mapping[str, LocalTool] | None = None,
    operator_principal: str | None = None,
    account_trace: AccountTrace | None = None,
):
    def stop_requested(state: ConversationState) -> bool:
        signal = state["stop"]
        return signal is not None and signal.is_set()

    async def call_model(state: ConversationState) -> dict:
        # The round after a round of tools: the calls resolved and were recorded, and this is where the
        # turn ends rather than asking the model what to do with them.
        if stop_requested(state):
            return {"pending": [], "stopped": True}

        parts: list[str] = []
        requests: list[ToolCallRequest] = []
        usage: UsageReport | None = None
        # Past the ceiling the model is called with no tools at all, rather than with tools it is told
        # not to use. A model holding none is simply answering.
        offered = state["tools"] if state["tool_calls_made"] < TOOL_CALL_CEILING else []
        try:
            async for chunk in provider.stream(
                model=state["model"],
                system_prompt=state["system_prompt"],
                given=Conversation(turns=state["history"]),
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
                if stop_requested(state):
                    # Leaving the loop closes the provider's stream. What arrived is kept, and the
                    # requests the model asked for are dropped rather than sent: they never left.
                    return {
                        "text": state["text"] + "".join(parts),
                        "usages": [*state["usages"], usage],
                        "pending": [],
                        "failed": False,
                        "stopped": True,
                    }
        except Exception:
            # Caught here, not by the caller: whatever text arrived before the provider broke must still
            # be returned. Logged with the traceback first, or the panel says "incomplete" with no record.
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

        async def through_the_server(
            request: ToolCallRequest, position: int
        ) -> tuple[ToolOutcome, int | None]:
            """One call to a tool server, with the trace it needs if it can move the account. The row comes
            first, so a process that dies between them leaves the `unknown` behind rather than nothing."""
            assert tool_server is not None
            if account_trace is None or not tool_server.moves_the_account(request.name):
                return (
                    await tool_server.call(request.name, request.arguments, operator_principal),
                    None,
                )
            try:
                row_id = await account_trace.begin(
                    round_index=round_index,
                    position=position,
                    name=request.name,
                    arguments=request.arguments,
                )
            except Exception:
                log.exception("no trace could be written for %s, so it was not sent", request.name)
                return (
                    ToolOutcome(
                        ToolOutcomeKind.UNAVAILABLE,
                        "this call was not sent: its record could not be written, and a "
                        "call that can change the account is never sent without one. Tell "
                        "the operator that rather than trying again.",
                        0,
                    ),
                    None,
                )
            outcome = await tool_server.call(request.name, request.arguments, operator_principal)
            try:
                await account_trace.settle(
                    row_id=row_id,
                    outcome=str(outcome.kind),
                    text=outcome.text,
                    duration_ms=outcome.duration_ms,
                )
            except Exception:
                # The row stays `unknown`, which is the honest reading of what this process
                # can now say: the call was made and its outcome is not written down.
                log.exception("the trace for %s (row %d) could not be settled", request.name, row_id)
            return outcome, row_id

        for request in state["pending"]:
            if made >= TOOL_CALL_CEILING:
                # Not executed, so neither recorded nor announced — an event here would put a call in the
                # operator's panel that never happened. The model still gets a result, or the turn never ends.
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

            row_id: int | None = None
            local = (local_tools or {}).get(request.name)
            if local is not None:
                try:
                    outcome = await local(request.arguments)
                except Exception as err:  # noqa: BLE001 - a broken local tool is not a broken turn
                    # Mirrors `ToolServer.call`'s own guard: a local tool can fail exactly as a remote one
                    # can, and without this the exception reaches a backstop that discards the whole turn.
                    log.warning("local tool %s failed: %s", request.name, err)
                    outcome = ToolOutcome(
                        ToolOutcomeKind.UNAVAILABLE,
                        f"this tool failed unexpectedly ({err}). Nothing was changed.",
                        0,
                    )
            elif tool_server is not None:
                outcome, row_id = await through_the_server(request, len(recorded))
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
                row_id=row_id,
            )
            recorded.append(call)
            # Announced before the loop moves on, so a round of three calls reaches the caller as three
            # events in the order they resolved. `recorded` holds this round alone.
            await state["on_tool_call"](call, len(recorded) - 1)

        return {
            "rounds": [*state["rounds"], ToolRound(tuple(state["pending"]), tuple(results))],
            "calls": [*state["calls"], *recorded],
            "tool_calls_made": made,
            "pending": [],
        }

    def after_model(state: ConversationState) -> str:
        if state["failed"] or state["stopped"] or not state["pending"]:
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
    stop: StopSignal | None = None,
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
        "stop": stop,
        "stopped": False,
    }
