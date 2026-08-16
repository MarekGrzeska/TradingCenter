from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from teams.contract import (
    AgentDefinition,
    CostLimits,
    CreateTeamIn,
    RunOut,
    RunStepOut,
    TeamDefinition,
    TeamEdge,
    TeamOut,
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


def test_a_blank_field_refuses() -> None:
    with pytest.raises(ValidationError, match="prompt"):
        AgentDefinition.model_validate(_agent("analyst", prompt="   "))


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


def test_edge_also_accepts_the_python_name_by_field_name() -> None:
    edge = TeamEdge(from_="analyst", to="trader")
    assert edge.model_dump(by_alias=True) == {"from": "analyst", "to": "trader"}


# --- CostLimits ---


def test_limits_default_to_none() -> None:
    assert CostLimits().run_limit is None


def test_a_non_numeric_limit_refuses() -> None:
    with pytest.raises(ValidationError, match="not a number"):
        CostLimits(run_limit="a lot")


def test_a_non_positive_limit_refuses() -> None:
    with pytest.raises(ValidationError, match="positive"):
        CostLimits(daily_limit="0")


def test_a_limit_round_trips_as_a_normalised_string() -> None:
    assert CostLimits(run_limit="1.50").run_limit == "1.50"


# --- TeamDefinition: structural validation ---


def test_a_single_agent_with_no_edges_is_valid() -> None:
    definition = TeamDefinition.model_validate({"agents": [_agent("solo")]})
    assert definition.agents[0].key == "solo"
    assert definition.edges == []


def test_several_independent_agents_with_no_edges_are_valid() -> None:
    # specs/teams-catalogue: a team with no dependencies at all is a choice, not a
    # mistake — every agent works in parallel, by design.
    definition = TeamDefinition.model_validate(
        {"agents": [_agent("a"), _agent("b"), _agent("c")]}
    )
    assert len(definition.agents) == 3


def test_no_agents_at_all_refuses() -> None:
    with pytest.raises(ValidationError, match="at least one agent"):
        TeamDefinition.model_validate({"agents": []})


def test_duplicate_agent_keys_refuse() -> None:
    with pytest.raises(ValidationError, match="duplicate agent keys"):
        TeamDefinition.model_validate({"agents": [_agent("a"), _agent("a")]})


def test_an_edge_naming_an_unknown_source_refuses() -> None:
    with pytest.raises(ValidationError, match="unknown agent 'ghost'"):
        TeamDefinition.model_validate(
            {"agents": [_agent("a")], "edges": [{"from": "ghost", "to": "a"}]}
        )


def test_an_edge_naming_an_unknown_target_refuses() -> None:
    with pytest.raises(ValidationError, match="unknown agent 'ghost'"):
        TeamDefinition.model_validate(
            {"agents": [_agent("a")], "edges": [{"from": "a", "to": "ghost"}]}
        )


def test_an_agent_depending_on_itself_refuses() -> None:
    with pytest.raises(ValidationError, match="depends on itself"):
        TeamDefinition.model_validate(
            {"agents": [_agent("a")], "edges": [{"from": "a", "to": "a"}]}
        )


def test_the_same_dependency_named_twice_refuses() -> None:
    with pytest.raises(ValidationError, match="more than once"):
        TeamDefinition.model_validate(
            {
                "agents": [_agent("a"), _agent("b")],
                "edges": [{"from": "a", "to": "b"}, {"from": "a", "to": "b"}],
            }
        )


def test_an_isolated_agent_among_connected_ones_refuses() -> None:
    # specs/teams-catalogue, "Agent, do którego nic nie prowadzi i który do niczego nie
    # prowadzi" — c has no edge at all while a and b are wired together.
    with pytest.raises(ValidationError, match="no dependency in either direction.*'c'"):
        TeamDefinition.model_validate(
            {
                "agents": [_agent("a"), _agent("b"), _agent("c")],
                "edges": [{"from": "a", "to": "b"}],
            }
        )


def test_a_simple_cycle_refuses() -> None:
    with pytest.raises(ValidationError, match="dependency cycle"):
        TeamDefinition.model_validate(
            {
                "agents": [_agent("a"), _agent("b")],
                "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "a"}],
            }
        )


def test_a_three_node_cycle_refuses() -> None:
    with pytest.raises(ValidationError, match="dependency cycle"):
        TeamDefinition.model_validate(
            {
                "agents": [_agent("a"), _agent("b"), _agent("c")],
                "edges": [
                    {"from": "a", "to": "b"},
                    {"from": "b", "to": "c"},
                    {"from": "c", "to": "a"},
                ],
            }
        )


def test_a_diamond_shaped_dag_is_valid() -> None:
    # analyst-h1 and analyst-d1 both feed trader — a fan-in, not a cycle.
    definition = TeamDefinition.model_validate(
        {
            "agents": [_agent("h1"), _agent("d1"), _agent("trader")],
            "edges": [{"from": "h1", "to": "trader"}, {"from": "d1", "to": "trader"}],
        }
    )
    assert len(definition.edges) == 2


def test_two_disconnected_pairs_are_both_valid() -> None:
    # Neither b nor d is isolated — each touches one edge — even though the two pairs
    # never connect to each other. Nothing in specs/teams-catalogue forbids this shape.
    definition = TeamDefinition.model_validate(
        {
            "agents": [_agent("a"), _agent("b"), _agent("c"), _agent("d")],
            "edges": [{"from": "a", "to": "b"}, {"from": "c", "to": "d"}],
        }
    )
    assert len(definition.agents) == 4


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


# --- Out models: from_row ---


def test_team_out_from_row() -> None:
    out = TeamOut.from_row(
        {
            "id": 1,
            "name": "Trend Desk",
            "description": "",
            "latest_revision": 3,
            "created_at": _now(),
            "updated_at": _now(),
        }
    )
    assert out.latest_revision == 3


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


def test_run_out_from_row() -> None:
    out = RunOut.from_row(
        {
            "id": 1,
            "team_revision_id": 10,
            "status": "completed",
            "stopped_reason": None,
            "started_at": _now(),
            "finished_at": _now(),
            "created_at": _now(),
        }
    )
    assert out.status == "completed"


def test_run_step_out_from_row() -> None:
    out = RunStepOut.from_row(
        {
            "id": 1,
            "run_id": 1,
            "agent_key": "analyst",
            "status": "completed",
            "output": "Cena rośnie.",
            "rounds": 2,
            "started_at": _now(),
            "finished_at": _now(),
        }
    )
    assert out.rounds == 2


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
