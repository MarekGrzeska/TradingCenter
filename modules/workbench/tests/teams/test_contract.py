from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from teams.contract import (
    MEMORY_ENTRY_MAX_CHARS,
    AgentDefinition,
    CostLimits,
    CreateTeamIn,
    MemoryEntryOut,
    TeamDefinition,
    TeamEdge,
    TeamMemoryOut,
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



def test_edge_accepts_the_wire_name_from() -> None:
    edge = TeamEdge.model_validate({"from": "analyst", "to": "trader"})
    assert edge.from_ == "analyst"
    assert edge.to == "trader"



def test_a_limit_round_trips_as_a_normalised_string() -> None:
    assert CostLimits(run_limit="1.50").run_limit == "1.50"


# Every refusal is one row rather than one function: they all take the same two lines, and a table shows at
# a glance which shapes are rejected and which are not.


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



def test_create_team_requires_a_name() -> None:
    with pytest.raises(ValidationError, match="blank"):
        CreateTeamIn.model_validate({"name": "   ", "definition": {"agents": [_agent("a")]}})


def test_create_team_collapses_whitespace_in_the_name() -> None:
    created = CreateTeamIn.model_validate(
        {"name": "  Trend   Desk  ", "definition": {"agents": [_agent("a")]}}
    )
    assert created.name == "Trend Desk"


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


def test_a_memory_entry_reads_a_row_as_it_stands() -> None:
    row = {
        "id": 7,
        "author_agent_key": "scout",
        "run_id": 12,
        "content": "gap opens usually close by noon",
        "created_at": datetime(2026, 8, 22, 9, 0, tzinfo=UTC),
    }

    entry = MemoryEntryOut.from_row(row)

    assert entry.id == 7
    assert entry.author_agent_key == "scout"
    assert entry.run_id == 12
    assert entry.content == "gap opens usually close by noon"


def test_an_entry_that_outlived_its_run_carries_no_run() -> None:
    row = {
        "id": 8,
        "author_agent_key": "scout",
        "run_id": None,
        "content": "still true",
        "created_at": datetime(2026, 8, 22, 9, 0, tzinfo=UTC),
    }

    assert MemoryEntryOut.from_row(row).run_id is None


def test_the_memory_read_says_how_much_it_did_not_hand_over() -> None:
    # specs/teams-memory, "Odczyt oddaje najnowsze wpisy, a nie całą pamięć".
    rows = [
        {
            "id": index,
            "author_agent_key": "scout",
            "run_id": None,
            "content": f"entry {index}",
            "created_at": datetime(2026, 8, 22, 9, 0, tzinfo=UTC),
        }
        for index in (3, 2)
    ]

    memory = TeamMemoryOut.from_rows(rows, total=9)

    assert [entry.content for entry in memory.entries] == ["entry 3", "entry 2"]
    assert memory.total == 9


def test_the_entry_ceiling_is_the_same_number_in_the_module_and_on_disk() -> None:
    """The length ceiling is stated twice on purpose — once here, once as a CHECK in migration 0008. Two
    statements of one number are a drift waiting to happen, so this is the test that notices."""
    migration = (
        Path(__file__).resolve().parents[2] / "migrations/teams/versions/0008_team_memories.py"
    )
    source = migration.read_text(encoding="utf-8")

    match = re.search(r"^_ENTRY_MAX_CHARS = (\d+)$", source, re.MULTILINE)

    assert match is not None, "migration 0008 no longer states its own entry ceiling"
    assert int(match.group(1)) == MEMORY_ENTRY_MAX_CHARS
