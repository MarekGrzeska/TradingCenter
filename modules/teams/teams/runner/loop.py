"""One agent's work: the model and its tools, going round until the model stops asking.

This is the inside of a node in the team's graph. `agent/graph.py` runs the same shape as
a two-node LangGraph with a conditional edge between them; here it is a plain loop, and
the reason is what surrounds it: the *team* graph is the LangGraph (`graph.py` next
door), built from the definition the operator drew, and nesting a second graph inside
every node of it would put two frameworks' worth of supersteps between an operator's
question and its answer. The round ceiling reads as a `for` bound, which is what it is.

Three failures stay apart, exactly as they do in `agent`:

- the **tool** refused — the server answered, and its answer names what to change. Back to
  the model, which can act on it.
- the tool **server** could not be reached — nothing was asked, so nothing is known about
  the archive either way. Also back to the model, worded so it does not read as missing
  data.
- the **provider** broke — nothing more will be generated. The agent's work ends with
  whatever text arrived, marked failed, and the run stops (specs/teams-runs, "Przebieg
  kończy się błędem w połowie").
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from ..contract import AgentDefinition
from ..provider import (
    ModelProvider,
    TextDelta,
    ToolCallRequest,
    ToolCallResult,
    ToolRound,
    UsageReport,
)
from ..tools import ToolDescriptor, ToolOutcome

log = logging.getLogger(__name__)

# How many times one agent may go model → tools → model. A number in the code rather than
# a setting, the same choice `agent` made for its own ceiling and for the same reason: a
# safety ceiling in configuration is an invitation to raise it at the moment it is
# inconvenient.
#
# Six, not agent's eight, and the difference is the multiplication. A conversation's
# ceiling bounds one turn; here every agent in a team carries its own, so a six-agent team
# is bounded at 6 × 6 model-plus-tools rounds before anyone has read a word of the result.
# Six still covers what a real analytical role does — coverage, candles, indicators,
# levels — with room for one retry.
ROUND_CEILING = 6


@dataclass(frozen=True)
class RecordedCall:
    """One resolved tool call, in the shape both the trace row and the progress event are
    built from — a panel and a reloaded run must not be able to disagree about what was
    asked and what came back."""

    round_index: int
    position: int
    name: str
    arguments: dict[str, Any]
    outcome: str
    text: str
    duration_ms: int


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
    # True when the loop hit `ROUND_CEILING` and the last model call was made with no
    # tools at all. `run_steps.rounds` carries the number; this is what says the number
    # was a ceiling rather than a coincidence (specs/teams-runs, "ślad przebiegu pokazuje,
    # że granica została osiągnięta").
    ceiling_reached: bool = False


ToolCaller = Callable[[str, dict[str, Any]], Awaitable[ToolOutcome]]
OnToolCall = Callable[[RecordedCall], Awaitable[None]]
# Called before each model call and allowed to raise — the cost ceiling's only way in
# (`cost.py`). Called after each one with what the provider reported, which is where the
# usage row is written.
BeforeModelCall = Callable[[], Awaitable[None]]
OnModelCall = Callable[[UsageReport | None], Awaitable[None]]


def system_prompt_for(agent: AgentDefinition, *, has_tools: bool) -> str:
    """The agent's own role and prompt, plus its guidance and one line about tools.

    Assembled here rather than stored: the definition carries what the operator wrote, and
    the sentence about tools depends on what this run could actually reach, which is not a
    property of the revision.
    """
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
    """What this agent is told, and the whole of it.

    `predecessors` is `(agent_key, output)` for the agents an edge leads *from* — nobody
    else's work appears here, which is the requirement itself (specs/teams-runs, "Agent
    widzi wypowiedzi poprzedników, a nie całą historię przebiegu"). An agent with no
    predecessors starts from its own prompt alone.
    """
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
) -> AgentWork:
    """Model → tools → model, until the model stops asking or the ceiling is reached.

    Never raises for a broken provider or a broken tool: both come back inside `AgentWork`,
    because the text an agent produced before something broke is part of the trace this
    module exists to keep.

    The two hooks are the exception, and they are deliberately outside that guarantee.
    `before_model_call` is what a cost ceiling raises from — a run stopped for money did
    not fail, and the difference has to reach the status (specs/teams-usage). `on_model_call`
    is where the usage row is written, once per call rather than once per agent: a limit
    checked against a total that only updates when an agent finishes would let a six-round
    agent spend six rounds past it.
    """
    work = AgentWork()
    system_prompt = system_prompt_for(agent, has_tools=bool(tools))
    rounds: list[ToolRound] = []

    while True:
        if before_model_call is not None:
            await before_model_call()
        at_ceiling = work.rounds >= ROUND_CEILING
        # Past the ceiling the model is called with no tools at all, rather than with
        # tools it is told not to use. A model holding a tool it may not call is being
        # asked to obey a rule; a model holding none is simply answering
        # (specs/teams-runs, "Po jej osiągnięciu agent MUST dokończyć pracę bez dalszego
        # sięgania po narzędzia").
        offered = [] if at_ceiling else list(tools)
        parts: list[str] = []
        requests: list[ToolCallRequest] = []
        usage: UsageReport | None = None
        try:
            async for chunk in provider.stream(
                model=model,
                system_prompt=system_prompt,
                briefing=briefing,
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
            )
            work.calls.append(call)
            # Announced as it resolves, not when the round ends: a round of three calls
            # reaches the operator as three events in the order they happened
            # (specs/teams-runs, "Postęp przebiegu widać w trakcie").
            await on_tool_call(call)

        rounds.append(ToolRound(tuple(requests), tuple(results)))
        work.rounds += 1
