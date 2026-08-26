"""One agent's work: the model and its tools, going round until the model stops asking. A plain loop, because the *team*
graph is the LangGraph, and three failures stay apart as they do in `agent`."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from ..contract import AgentDefinition
from ..provider import (
    Briefing,
    ModelProvider,
    TextDelta,
    ToolCallRequest,
    ToolCallResult,
    ToolRound,
    UsageReport,
)
from ..tools import ToolDescriptor, ToolOutcome, ToolOutcomeKind

log = logging.getLogger(__name__)

# How many times one agent may go model → tools → model. In the code rather than a setting: a safety
# ceiling in configuration is an invitation to raise it. Six, not agent's eight, because here it multiplies.
ROUND_CEILING = 6


@dataclass(frozen=True)
class RecordedCall:
    """One resolved tool call, in the shape both the trace row and the progress event are built from — a
    panel and a reloaded run must not disagree about what was asked and what came back."""

    round_index: int
    position: int
    name: str
    arguments: dict[str, Any]
    outcome: str
    text: str
    duration_ms: int
    # Whether the tool's own server declared it as changing the account. Carried on the call rather than
    # looked up again: a second lookup elsewhere would be a second place that could disagree.
    writes: bool = False


@dataclass
class AgentWork:
    """Everything one agent leaves behind, whether it finished or broke."""

    text: str = ""
    rounds: int = 0
    calls: list[RecordedCall] = field(default_factory=list)
    # One per model call, in order. An agent that used tools was billed more than once,
    # and every one of those calls leaves its own usage row (specs/teams-usage).
    usages: list[UsageReport | None] = field(default_factory=list)
    failed: bool = False
    # True when the loop hit `ROUND_CEILING` and the last model call was made with no tools. `rounds`
    # carries the number; this says the number was a ceiling rather than a coincidence.
    ceiling_reached: bool = False


ToolCaller = Callable[[str, dict[str, Any]], Awaitable[ToolOutcome]]
OnToolCall = Callable[[RecordedCall], Awaitable[None]]
# Called before each model call and allowed to raise — the cost ceiling's only way in. Called after each
# one with what the provider reported, which is where the usage row is written.
BeforeModelCall = Callable[[], Awaitable[None]]
OnModelCall = Callable[[UsageReport | None], Awaitable[None]]
# Called before a call to a tool its server declared as changing the account, and only for those. Three
# things it may do: raise (the run stops), answer with a sentence (this call is refused), or answer `None`.
BeforeWriteCall = Callable[[str, dict[str, Any]], Awaitable[str | None]]

# Whether a tool name could leave the account changed. Answered by `ToolPlan` off the same announcement the
# run was admitted on — never re-derived here, which is how two modules read one hint in opposite directions.
MovesTheAccount = Callable[[str], bool]


def system_prompt_for(agent: AgentDefinition, *, has_tools: bool) -> str:
    """The agent's own role and prompt, plus its guidance and one line about tools. Assembled here rather
    than stored: the sentence about tools depends on what this run could reach, not on the revision."""
    parts = [f"You are the {agent.role} in a team of agents working on one question.", agent.prompt]
    if agent.guidance.strip():
        parts.append(agent.guidance.strip())
    parts.append(
        "You have tools. Use them to check facts rather than recalling them; say plainly "
        "when a tool could not answer."
        if has_tools
        else "You have no tools in this run. Answer from what you were given, and say "
        "which claims you could not check."
    )
    parts.append(
        "End with your conclusion for the team. It is read by the agents that depend on "
        "you, and nothing you write places an order — this module trades nothing."
    )
    return "\n\n".join(parts)


def briefing_for(agent: AgentDefinition, predecessors: Sequence[tuple[str, str]]) -> str:
    """What this agent is told, and the whole of it. `predecessors` is `(agent_key, output)` for the agents
    an edge leads *from* — nobody else's work appears, which is the requirement itself."""
    if not predecessors:
        return "You are starting. Nobody has worked before you in this run."
    parts = ["The agents you depend on have finished. This is their work."]
    parts.extend(f"--- {key} ---\n{output}" for key, output in predecessors)
    return "\n\n".join(parts)


async def run_agent(
    agent: AgentDefinition,
    *,
    model: str,
    briefing: str,
    provider: ModelProvider,
    tools: Sequence[ToolDescriptor],
    call_tool: ToolCaller,
    on_tool_call: OnToolCall,
    before_model_call: BeforeModelCall | None = None,
    on_model_call: OnModelCall | None = None,
    before_write_call: BeforeWriteCall | None = None,
    moves_the_account: MovesTheAccount | None = None,
) -> AgentWork:
    """Model → tools → model, until the model stops asking or the ceiling is reached. Never raises for a broken provider
    or tool — the text produced before it broke is part of the trace — but the hooks are outside that guarantee."""
    work = AgentWork()
    system_prompt = system_prompt_for(agent, has_tools=bool(tools))
    rounds: list[ToolRound] = []

    while True:
        if before_model_call is not None:
            await before_model_call()
        at_ceiling = work.rounds >= ROUND_CEILING
        # Past the ceiling the model is called with no tools at all, rather than with tools it is told
        # not to use. A model holding none is simply answering.
        offered = [] if at_ceiling else list(tools)
        parts: list[str] = []
        requests: list[ToolCallRequest] = []
        usage: UsageReport | None = None
        try:
            async for chunk in provider.stream(
                model=model,
                system_prompt=system_prompt,
                given=Briefing(text=briefing),
                tools=offered,
                rounds=rounds,
            ):
                if isinstance(chunk, TextDelta):
                    parts.append(chunk.text)
                elif isinstance(chunk, ToolCallRequest):
                    requests.append(chunk)
                else:
                    usage = chunk
        except Exception:
            # Logged with its traceback before it becomes a flag: without this line the
            # operator sees a failed step and nothing anywhere says what broke.
            log.exception("the model call failed for agent %s after %d round(s)", agent.key, work.rounds)
            work.text += "".join(parts)
            work.usages.append(usage)
            if on_model_call is not None:
                # The call happened and was billed, however it ended — a row written only
                # for calls that succeeded would under-report the bill (specs/teams-usage).
                await on_model_call(usage)
            work.failed = True
            return work

        work.text += "".join(parts)
        work.usages.append(usage)
        if on_model_call is not None:
            await on_model_call(usage)

        if not requests or at_ceiling:
            # At the ceiling the model was offered nothing, so anything it asked for could
            # not have been a tool call; either way this was the last call.
            work.ceiling_reached = at_ceiling
            return work

        results: list[ToolCallResult] = []
        for position, request in enumerate(requests):
            # Not decided here. The plan holds both the announcement and which server it came from, and
            # answers conservatively: unannotated on a server that can send orders reads as an order.
            writes = moves_the_account(request.name) if moves_the_account is not None else False

            refusal: str | None = None
            if writes and before_write_call is not None:
                # Raises to stop the run (an exhausted count), or answers with a sentence to refuse this
                # one call and carry on (a size the agent can correct).
                refusal = await before_write_call(request.name, request.arguments)

            if refusal is not None:
                outcome = ToolOutcome(ToolOutcomeKind.REFUSED, refusal, 0)
            else:
                outcome = await call_tool(request.name, request.arguments)

            results.append(ToolCallResult(id=request.id, name=request.name, text=outcome.text))
            call = RecordedCall(
                round_index=work.rounds,
                position=position,
                name=request.name,
                arguments=request.arguments,
                outcome=str(outcome.kind),
                text=outcome.text,
                duration_ms=outcome.duration_ms,
                writes=writes,
            )
            work.calls.append(call)
            # Announced as it resolves, not when the round ends: a round of three calls reaches the
            # operator as three events in the order they happened.
            await on_tool_call(call)

        rounds.append(ToolRound(tuple(requests), tuple(results)))
        work.rounds += 1
