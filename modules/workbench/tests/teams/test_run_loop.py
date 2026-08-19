"""One agent's model-and-tools loop: what it is told, when it stops, and what it leaves
behind when something breaks."""

from __future__ import annotations

from teams.contract import AgentDefinition
from teams.runner import ROUND_CEILING, RecordedCall, run_agent
from teams.runner.loop import briefing_for, system_prompt_for
from teams.tools import ToolDescriptor, ToolOutcome, ToolOutcomeKind

from .scripted_provider import ScriptedProvider, always_asks_for_tool, asks_for_tool, breaks, says

PRICE_TOOL = ToolDescriptor(
    name="get_last_price",
    description="The last price for a symbol.",
    input_schema={"type": "object", "properties": {"symbol": {"type": "string"}}},
)


def an_agent(**overrides) -> AgentDefinition:
    fields = {
        "key": "reader",
        "role": "reader",
        "prompt": "read the market",
        "model_id": "gpt-5.6-luna",
        "tools": [],
    }
    return AgentDefinition(**{**fields, **overrides})


async def _run(agent: AgentDefinition, provider: ScriptedProvider, *, tools=(), outcome=None):
    calls: list[RecordedCall] = []

    async def call_tool(name: str, arguments: dict) -> ToolOutcome:
        del name, arguments
        return outcome or ToolOutcome(ToolOutcomeKind.OK, "21000.5", 12)

    async def on_tool_call(call: RecordedCall) -> None:
        calls.append(call)

    work = await run_agent(
        agent,
        model="luna-prod",
        briefing="start here",
        provider=provider,
        tools=tools,
        call_tool=call_tool,
        on_tool_call=on_tool_call,
    )
    return work, calls


async def test_an_agent_without_tools_answers_in_one_call() -> None:
    provider = ScriptedProvider(default=says("US100 looks weak."))

    work, calls = await _run(an_agent(), provider)

    assert work.text == "US100 looks weak."
    assert work.rounds == 0
    assert calls == []
    assert len(work.usages) == 1


async def test_a_tool_round_bills_twice_and_leaves_a_call() -> None:
    """specs/teams-usage: every model call leaves its own usage row, and an agent that
    used a tool was called at least twice."""
    provider = ScriptedProvider(
        default=asks_for_tool("get_last_price", {"symbol": "US100"}, then="It is 21000.5.")
    )

    work, calls = await _run(an_agent(), provider, tools=[PRICE_TOOL])

    assert work.text == "It is 21000.5."
    assert work.rounds == 1
    assert len(work.usages) == 2
    assert [call.name for call in calls] == ["get_last_price"]
    assert calls[0].round_index == 0 and calls[0].position == 0
    assert calls[0].outcome == "ok"


async def test_the_round_ceiling_stops_the_asking_and_shows_in_the_work() -> None:
    """specs/teams-runs, "Agent osiąga granicę rund": the next call is made with no tools
    at all, and the trace says the ceiling was reached."""
    provider = ScriptedProvider(default=always_asks_for_tool("get_last_price"))

    work, calls = await _run(an_agent(), provider, tools=[PRICE_TOOL])

    assert work.rounds == ROUND_CEILING
    assert work.ceiling_reached is True
    assert len(calls) == ROUND_CEILING
    # The last call was offered nothing — a model holding a tool it may not use is being
    # asked to obey a rule; one holding none is simply answering.
    assert provider.asks[-1].tool_names == ()
    assert all(ask.tool_names == ("get_last_price",) for ask in provider.asks[:-1])


async def test_a_broken_provider_keeps_the_text_that_arrived() -> None:
    provider = ScriptedProvider(default=breaks("connection reset"))

    work, _ = await _run(an_agent(), provider)

    assert work.failed is True
    # A usage entry is still appended: the call happened, and what it cost is unknown
    # rather than zero (specs/teams-usage).
    assert work.usages == [None]


async def test_a_refused_tool_goes_back_to_the_model_as_a_result() -> None:
    """The refusal is a result, not an outage — the agent can act on the sentence."""
    provider = ScriptedProvider(
        default=asks_for_tool("get_last_price", {"symbol": "NOPE"}, then="Nobody collects it.")
    )
    refusal = ToolOutcome(ToolOutcomeKind.REFUSED, "nobody collects NOPE.", 5)

    work, calls = await _run(an_agent(), provider, tools=[PRICE_TOOL], outcome=refusal)

    assert work.failed is False
    assert calls[0].outcome == "refused"
    assert work.text == "Nobody collects it."


async def test_an_unavailable_server_is_a_different_fact_in_the_trace() -> None:
    provider = ScriptedProvider(
        default=asks_for_tool("get_last_price", {"symbol": "US100"}, then="Could not check.")
    )
    outage = ToolOutcome(ToolOutcomeKind.UNAVAILABLE, "the tool server could not be reached", 3)

    _, calls = await _run(an_agent(), provider, tools=[PRICE_TOOL], outcome=outage)

    assert calls[0].outcome == "unavailable"


def test_the_briefing_carries_predecessors_and_nothing_else() -> None:
    """specs/teams-runs, "Agent widzi wypowiedzi poprzedników, a nie całą historię
    przebiegu"."""
    briefing = briefing_for(an_agent(key="judge"), [("scout", "the trend is up")])

    assert "the trend is up" in briefing
    assert "scout" in briefing


def test_an_agent_with_no_predecessors_is_told_so() -> None:
    assert "starting" in briefing_for(an_agent(), [])


def test_the_system_prompt_says_whether_this_run_has_tools() -> None:
    with_tools = system_prompt_for(an_agent(guidance="be brief"), has_tools=True)
    without = system_prompt_for(an_agent(), has_tools=False)

    assert "be brief" in with_tools
    assert "no tools in this run" in without
    # Both name the one thing this phase does not do (proposal.md, "Faza 1 nie składa
    # zleceń") — a role told to decide should not be left inferring it may act.
    assert "places an order" in with_tools and "places an order" in without
