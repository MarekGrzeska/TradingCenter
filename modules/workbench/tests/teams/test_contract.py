from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from teams.contract import (
    AgentDefinition,
    CostLimits,
    CreateTeamIn,
    TeamDefinition,
    TeamEdge,
    TeamRevisionOut,
    ToolCallOut,
    UsageOut,
)


def _agent(key: str, **overrides) -> dict:
    return {
        "key": key,
        "role": "Analityk",
        "prompt": "Przeanalizuj wykres.",
        "model_id": "gpt-5.6-luna",
        **overrides,
    }


def _now() -> datetime:
    return datetime(2026, 8, 16, tzinfo=UTC)


# --- AgentDefinition ---


def test_a_complete_agent_builds() -> None:
    agent = AgentDefinition.model_validate(_agent("analyst", tools=["get_candles"]))
    assert agent.key == "analyst"
    assert agent.tools == ["get_candles"]
    assert agent.guidance == ""


def test_duplicate_tools_refuse() -> None:
    with pytest.raises(ValidationError, match="same tool twice"):
        AgentDefinition.model_validate(_agent("analyst", tools=["get_candles", "get_candles"]))


def test_a_blank_tool_name_refuses() -> None:
    with pytest.raises(ValidationError, match="blank"):
        AgentDefinition.model_validate(_agent("analyst", tools=["  "]))


# --- TeamEdge: the `from` alias ---


def test_edge_accepts_the_wire_name_from() -> None:
    edge = TeamEdge.model_validate({"from": "analyst", "to": "trader"})
    assert edge.from_ == "analyst"
    assert edge.to == "trader"


# --- CostLimits: the string a limit normalises to ---


def test_a_limit_round_trips_as_a_normalised_string() -> None:
    assert CostLimits(run_limit="1.50").run_limit == "1.50"


# --- TeamDefinition: the shape of the graph, which is the real logic here ---
#
# specs/teams-catalogue. Every refusal is one row rather than one function: they all take
# the same two lines to write, and a table shows at a glance which shapes are rejected and
# which are not — which is the thing a reader of this file came for.


@pytest.mark.parametrize(
    ("edges", "agents", "message"),
    [
        pytest.param([], [], "at least one agent", id="no agents at all"),
        pytest.param([], ["a", "a"], "duplicate agent keys", id="duplicate agent keys"),
        pytest.param(
            [("ghost", "a")], ["a"], "unknown agent 'ghost'", id="an edge from an unknown agent"
        ),
        pytest.param(
            [("a", "ghost")], ["a"], "unknown agent 'ghost'", id="an edge to an unknown agent"
        ),
        pytest.param([("a", "a")], ["a"], "depends on itself", id="an agent depending on itself"),
        pytest.param(
            [("a", "b"), ("a", "b")],
            ["a", "b"],
            "more than once",
            id="the same dependency named twice",
        ),
        pytest.param(
            [("a", "b")],
            ["a", "b", "c"],
            "no dependency in either direction.*'c'",
            # "Agent, do którego nic nie prowadzi i który do niczego nie prowadzi" — c has
            # no edge at all while a and b are wired together.
            id="an isolated agent among connected ones",
        ),
        pytest.param(
            [("a", "b"), ("b", "a")], ["a", "b"], "dependency cycle", id="a two-node cycle"
        ),
        pytest.param(
            [("a", "b"), ("b", "c"), ("c", "a")],
            ["a", "b", "c"],
            "dependency cycle",
            id="a three-node cycle",
        ),
    ],
)
def test_a_definition_that_is_not_a_dag_refuses(edges, agents, message) -> None:
    with pytest.raises(ValidationError, match=message):
        TeamDefinition.model_validate(
            {
                "agents": [_agent(key) for key in agents],
                "edges": [{"from": a, "to": b} for a, b in edges],
            }
        )


@pytest.mark.parametrize(
    ("edges", "agents"),
    [
        pytest.param([], ["solo"], id="a single agent with no edges"),
        # A team with no dependencies at all is a choice, not a mistake — every agent
        # works in parallel, by design.
        pytest.param([], ["a", "b", "c"], id="several independent agents with no edges"),
        # A fan-in, not a cycle: two analysts both feeding one trader.
        pytest.param(
            [("h1", "trader"), ("d1", "trader")], ["h1", "d1", "trader"], id="a diamond"
        ),
        # Neither b nor d is isolated — each touches one edge — even though the two pairs
        # never connect to each other. Nothing in the spec forbids this shape.
        pytest.param(
            [("a", "b"), ("c", "d")], ["a", "b", "c", "d"], id="two disconnected pairs"
        ),
    ],
)
def test_a_definition_that_is_a_dag_builds(edges, agents) -> None:
    definition = TeamDefinition.model_validate(
        {
            "agents": [_agent(key) for key in agents],
            "edges": [{"from": a, "to": b} for a, b in edges],
        }
    )

    assert [agent.key for agent in definition.agents] == agents
    assert len(definition.edges) == len(edges)


def test_limits_default_when_omitted() -> None:
    definition = TeamDefinition.model_validate({"agents": [_agent("solo")]})
    assert definition.limits.run_limit is None
    assert definition.limits.daily_limit is None


# --- CreateTeamIn ---


def test_create_team_requires_a_name() -> None:
    with pytest.raises(ValidationError, match="blank"):
        CreateTeamIn.model_validate({"name": "   ", "definition": {"agents": [_agent("a")]}})


def test_create_team_collapses_whitespace_in_the_name() -> None:
    created = CreateTeamIn.model_validate(
        {"name": "  Trend   Desk  ", "definition": {"agents": [_agent("a")]}}
    )
    assert created.name == "Trend Desk"


# --- Out models: the `from_row` steps that are more than a column rename ---
#
# A row whose fields land on the model one for one is Pydantic's own behaviour and was
# tested here three times over; what is left is the decoding these models actually do.


def test_team_revision_out_parses_jsonb_text() -> None:
    # asyncpg hands JSONB back as text unless a codec is registered — the row this
    # models a real query result, not a pre-decoded dict.
    row = {
        "id": 10,
        "team_id": 1,
        "version": 1,
        "definition": '{"agents": [{"key": "solo", "role": "Analityk", '
        '"prompt": "Patrz.", "model_id": "gpt-5.6-luna"}]}',
        "created_at": _now(),
    }
    out = TeamRevisionOut.from_row(row)
    assert out.definition.agents[0].key == "solo"


def test_team_revision_out_accepts_an_already_decoded_dict() -> None:
    row = {
        "id": 10,
        "team_id": 1,
        "version": 1,
        "definition": {"agents": [_agent("solo")]},
        "created_at": _now(),
    }
    out = TeamRevisionOut.from_row(row)
    assert out.definition.agents[0].key == "solo"


def test_tool_call_out_parses_jsonb_arguments() -> None:
    out = ToolCallOut.from_row(
        {
            "id": 1,
            "run_step_id": 1,
            "round_index": 0,
            "position": 0,
            "tool_name": "get_candles",
            "arguments": '{"symbol": "EURUSD"}',
            "outcome": "ok",
            "result_text": "...",
            "duration_ms": 120,
            "created_at": _now(),
        }
    )
    assert out.arguments == {"symbol": "EURUSD"}


def test_usage_out_stringifies_cost() -> None:
    out = UsageOut.from_row(
        {
            "id": 1,
            "run_id": 1,
            "run_step_id": 1,
            "model_id": "gpt-5.6-luna",
            "input_tokens": 100,
            "output_tokens": 50,
            "cached_tokens": None,
            "reasoning_tokens": None,
            "cost": Decimal("0.00012500"),
            "created_at": _now(),
        }
    )
    assert out.cost == "0.00012500"


def test_usage_out_keeps_a_missing_cost_as_none_not_zero() -> None:
    # specs/teams-usage: "no tokens reported" MUST NOT read as "zero cost".
    out = UsageOut.from_row(
        {
            "id": 1,
            "run_id": 1,
            "run_step_id": 1,
            "model_id": "gpt-5.6-luna",
            "input_tokens": None,
            "output_tokens": None,
            "cached_tokens": None,
            "reasoning_tokens": None,
            "cost": None,
            "created_at": _now(),
        }
    )
    assert out.cost is None
