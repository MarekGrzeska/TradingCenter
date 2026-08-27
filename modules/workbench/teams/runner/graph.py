"""The definition compiled to something executable: one node per agent and the edges the operator drew. What is written
here is the third property LangGraph does not give — each node is handed only its predecessors' outputs."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from ..contract import AgentDefinition, TeamDefinition


class AgentFailed(RuntimeError):
    """One agent could not finish. Raised out of its node, which stops the run — the work of everyone who
    finished before it stays written."""

    def __init__(self, agent_key: str, reason: str) -> None:
        super().__init__(f"agent {agent_key!r} failed: {reason}")
        self.agent_key = agent_key
        self.reason = reason


def _merge_outputs(left: dict[str, str], right: dict[str, str]) -> dict[str, str]:
    """Two agents finishing in the same superstep each return their own key. Without a reducer LangGraph
    refuses concurrent writes to one channel, which is why the state is a dict of outputs."""
    return {**left, **right}


class RunState(TypedDict):
    outputs: Annotated[dict[str, str], _merge_outputs]


# What a node does with one agent: given the agent and its predecessors' work, produce that agent's own
# output. Supplied by the engine — this module knows the shape of the work, not how it is done.
AgentRunner = Callable[[AgentDefinition, Sequence[tuple[str, str]]], Awaitable[str]]


def _predecessors_of(definition: TeamDefinition) -> dict[str, tuple[str, ...]]:
    """Agent key → the keys of the agents an edge leads from, in the definition's own
    order so two runs of one revision brief an agent identically."""
    incoming: dict[str, list[str]] = {agent.key: [] for agent in definition.agents}
    for edge in definition.edges:
        incoming[edge.to].append(edge.from_)
    order = [agent.key for agent in definition.agents]
    return {key: tuple(sorted(sources, key=order.index)) for key, sources in incoming.items()}


def compile_team(definition: TeamDefinition, run_agent: AgentRunner):
    """A compiled graph whose `ainvoke({"outputs": {}})` runs the whole team."""
    predecessors = _predecessors_of(definition)
    has_successor = {edge.from_ for edge in definition.edges}

    graph = StateGraph(RunState)

    for agent in definition.agents:
        graph.add_node(agent.key, _make_node(agent, predecessors[agent.key], run_agent))

    for agent in definition.agents:
        sources = predecessors[agent.key]
        if sources:
            # The list form is load-bearing: separate `add_edge` calls are independent triggers, so
            # predecessors finishing in different supersteps ran the node once per wave. Measured 21 Aug 2026.
            graph.add_edge(list(sources), agent.key)
        else:
            graph.add_edge(START, agent.key)
        if agent.key not in has_successor:
            graph.add_edge(agent.key, END)

    return graph.compile()


def _make_node(agent: AgentDefinition, sources: tuple[str, ...], run_agent: AgentRunner):
    async def node(state: RunState) -> dict:
        outputs = state["outputs"]
        # `.get` rather than `[]`, and the missing case is deliberate rather than defensive: a predecessor
        # that produced nothing readable is still a predecessor, and its successor should be told so.
        given = [(key, outputs.get(key, "")) for key in sources]
        return {"outputs": {agent.key: await run_agent(agent, given)}}

    return node
