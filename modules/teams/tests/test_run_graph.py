"""The definition compiled to a graph: who waits for whom, who works at the same time,
and who sees whose work."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

import pytest

from teams.contract import AgentDefinition, TeamDefinition, TeamEdge
from teams.runner import AgentFailed, compile_team


def an_agent(key: str) -> AgentDefinition:
    return AgentDefinition(key=key, role=key, prompt=f"be the {key}", model_id="gpt-5.6-luna")


def a_team(keys: list[str], edges: list[tuple[str, str]]) -> TeamDefinition:
    return TeamDefinition(
        agents=[an_agent(key) for key in keys],
        edges=[TeamEdge(from_=source, to=target) for source, target in edges],
    )


class Recorder:
    """Runs every agent instantly and remembers what each was given."""

    def __init__(self) -> None:
        self.given: dict[str, list[tuple[str, str]]] = {}
        self.order: list[str] = []

    async def __call__(self, agent: AgentDefinition, given: Sequence[tuple[str, str]]) -> str:
        self.given[agent.key] = list(given)
        self.order.append(agent.key)
        return f"{agent.key} says so"


async def test_an_agent_waits_for_every_predecessor() -> None:
    """specs/teams-runs, "Rola zbierająca wyniki dwóch innych"."""
    definition = a_team(["left", "right", "judge"], [("left", "judge"), ("right", "judge")])
    recorder = Recorder()

    await compile_team(definition, recorder).ainvoke({"outputs": {}})

    assert recorder.order.index("judge") == 2
    assert dict(recorder.given["judge"]) == {
        "left": "left says so",
        "right": "right says so",
    }


async def test_agents_without_a_dependency_between_them_work_at_the_same_time() -> None:
    """specs/teams-runs, "Dwie role bez zależności między sobą". Proven by making both
    wait for the other to have started — a sequential runner deadlocks, and the test would
    time out rather than pass quietly."""
    definition = a_team(["left", "right", "judge"], [("left", "judge"), ("right", "judge")])
    both_started = asyncio.Barrier(2)

    async def run_one(agent: AgentDefinition, given: Sequence[tuple[str, str]]) -> str:
        del given
        if agent.key in ("left", "right"):
            async with asyncio.timeout(5):
                await both_started.wait()
        return f"{agent.key} says so"

    await compile_team(definition, run_one).ainvoke({"outputs": {}})


async def test_an_agent_is_given_nothing_from_an_agent_it_does_not_depend_on() -> None:
    """specs/teams-runs, "Rola nie sąsiadująca z inną"."""
    definition = a_team(
        ["scout", "loner", "judge"], [("scout", "judge"), ("loner", "judge")]
    )
    recorder = Recorder()
    await compile_team(definition, recorder).ainvoke({"outputs": {}})

    # And the narrower case: two agents in one run with no edge between them.
    parallel = a_team(["a", "b", "sink"], [("a", "sink"), ("b", "sink")])
    recorder = Recorder()
    await compile_team(parallel, recorder).ainvoke({"outputs": {}})

    assert recorder.given["a"] == []
    assert recorder.given["b"] == []


async def test_a_team_with_no_edges_runs_every_agent_on_its_own() -> None:
    definition = a_team(["one", "two"], [])
    recorder = Recorder()

    await compile_team(definition, recorder).ainvoke({"outputs": {}})

    assert sorted(recorder.order) == ["one", "two"]
    assert recorder.given == {"one": [], "two": []}


async def test_a_failing_agent_stops_the_run() -> None:
    definition = a_team(["scout", "judge"], [("scout", "judge")])
    reached: list[str] = []

    async def run_one(agent: AgentDefinition, given: Sequence[tuple[str, str]]) -> str:
        del given
        reached.append(agent.key)
        if agent.key == "scout":
            raise AgentFailed("scout", "the model call failed")
        return "never"

    with pytest.raises(AgentFailed):
        await compile_team(definition, run_one).ainvoke({"outputs": {}})

    # The successor was never called: its predecessor never finished.
    assert reached == ["scout"]


async def test_predecessors_arrive_in_the_definitions_own_order() -> None:
    """Two runs of one revision must brief an agent identically — an order that depends on
    which predecessor happened to finish first would make them incomparable."""
    definition = a_team(["b", "a", "judge"], [("a", "judge"), ("b", "judge")])
    recorder = Recorder()

    await compile_team(definition, recorder).ainvoke({"outputs": {}})

    assert [key for key, _ in recorder.given["judge"]] == ["b", "a"]
