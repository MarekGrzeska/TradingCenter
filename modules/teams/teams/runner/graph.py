"""The definition compiled to something that can be executed: one node per agent, the
edges the operator drew, and nothing else.

LangGraph carries this because its model — explicit nodes and explicit edges — maps one to
one onto what a revision already stores (design.md, "LangGraph, nie OpenAI Agents SDK").
Two properties come with it rather than being written here:

- **an agent starts when its predecessors have finished**, because that is what an edge
  means to a graph runtime;
- **agents whose dependencies are already satisfied run at the same time**, because
  LangGraph runs one superstep's nodes concurrently (specs/teams-runs, "Agenci, których
  zależności są już spełnione, MAY pracować równocześnie").

What is written here is the third: each node is handed *only* its own predecessors'
outputs, never the whole state. The state holds every agent's work — a shared dict is how
LangGraph passes anything at all — so this file is where the narrowing has to happen, and
`_predecessors_of` is the whole of it (specs/teams-runs, "Agent widzi wypowiedzi
poprzedników, a nie całą historię przebiegu").

The definition is already known to be acyclic and connected: `TeamDefinition` refuses a
cycle, a self-edge and an isolated agent at the moment it is saved, so nothing here
re-checks any of that.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from ..contract import AgentDefinition, TeamDefinition


class AgentFailed(RuntimeError):
    """One agent could not finish. Raised out of its node, which stops the run — the work
    of everyone who finished before it stays written (specs/teams-runs, "Ślad przebiegu
    zostaje niezależnie od tego, jak przebieg się skończył")."""

    def __init__(self, agent_key: str, reason: str) -> None:
        super().__init__(f"agent {agent_key!r} failed: {reason}")
        self.agent_key = agent_key
        self.reason = reason


def _merge_outputs(left: dict[str, str], right: dict[str, str]) -> dict[str, str]:
    """Two agents finishing in the same superstep each return their own key. Without a
    reducer LangGraph refuses concurrent writes to one channel — this is the whole reason
    the state is a dict of outputs rather than a list."""
    return {**left, **right}


class RunState(TypedDict):
    outputs: Annotated[dict[str, str], _merge_outputs]


# What a node does with one agent: given the agent and its predecessors' work, produce
# that agent's own output. Supplied by the engine, which is where the model, the tools and
# the trace live — this module knows only the shape of the work, not how it is done.
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
        if not predecessors[agent.key]:
            graph.add_edge(START, agent.key)
        if agent.key not in has_successor:
            graph.add_edge(agent.key, END)

    for edge in definition.edges:
        graph.add_edge(edge.from_, edge.to)

    return graph.compile()


def _make_node(agent: AgentDefinition, sources: tuple[str, ...], run_agent: AgentRunner):
    async def node(state: RunState) -> dict:
        outputs = state["outputs"]
        # `.get` rather than `[]`, and the missing case is deliberate rather than
        # defensive: a predecessor that produced nothing readable is still a predecessor,
        # and its successor should be told that instead of dying on a KeyError.
        given = [(key, outputs.get(key, "")) for key in sources]
        return {"outputs": {agent.key: await run_agent(agent, given)}}

    return node
