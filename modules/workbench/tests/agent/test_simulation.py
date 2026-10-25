"""The simulated model (`agent-simulated-model`): what it is allowed to be chosen in, and how a scenario plays a turn."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent.provider import Conversation, TextDelta, ToolCallRequest, ToolRound, UsageReport
from agent.simulation import Scenario, ScenarioError, SimulatedProvider, load_scenario

from .test_config import settings

DRAFT = {
    "turns": [
        {
            "when": r"^E2E szkic (?<id>\d+)$",
            "rounds": [
                {"tools": [{"name": "draft_strategy", "arguments": {"strategy_id": "{id}", "note": "for {id}"}}]},
                {"say": "Wpisałem szkic."},
            ],
        }
    ]
}


async def _play(scenario: dict, message: str, rounds: int = 0) -> list:
    provider = SimulatedProvider(Scenario.model_validate(scenario))
    given = Conversation(turns=[("operator", "earlier"), ("agent", "ok"), ("operator", message)])
    done = [ToolRound(calls=(), results=())] * rounds
    return [chunk async for chunk in provider.stream(model="m", system_prompt="", given=given, rounds=done)]


def test_the_simulation_is_refused_where_database_user_is_set() -> None:
    with pytest.raises(ValidationError, match="DATABASE_USER"):
        settings(provider="sim", sim_scenario="scenario.json")


def test_the_simulation_needs_its_scenario_and_nothing_else_is_a_provider() -> None:
    with pytest.raises(ValidationError, match="AGENT_SIM_SCENARIO"):
        settings(provider="sim", database_user=None, database_url="postgresql://u:p@127.0.0.1:5432/agent")
    with pytest.raises(ValidationError, match="openai"):
        settings(provider="claude")


async def test_a_matching_rule_asks_for_its_tool_with_the_group_filled_in_then_says_its_text() -> None:
    first = await _play(DRAFT, "E2E szkic 7")
    second = await _play(DRAFT, "E2E szkic 7", rounds=1)

    assert first == [
        ToolCallRequest(id="sim-0-0", name="draft_strategy", arguments={"strategy_id": 7, "note": "for 7"}),
        UsageReport(0, 0, None, None),
    ]
    assert second == [TextDelta("Wpisałem szkic."), UsageReport(0, 0, None, None)]


async def test_a_message_no_rule_knows_is_answered_not_failed() -> None:
    chunks = await _play(DRAFT, "hello")

    assert isinstance(chunks[0], TextDelta) and "scenariusz nie zna" in chunks[0].text


@pytest.mark.parametrize(
    "broken",
    [
        "not json",
        json.dumps({"turns": []}),
        json.dumps({"turns": [{"when": "x", "rounds": [{"tools": [{"name": "t"}]}]}]}),
        json.dumps({"turns": [{"when": "x", "rounds": [{"say": "a", "tools": [{"name": "t"}]}]}]}),
        json.dumps({"turns": [{"when": "(", "rounds": [{"say": "a"}]}]}),
    ],
)
def test_a_scenario_that_breaks_its_rules_is_refused(tmp_path: Path, broken: str) -> None:
    path = tmp_path / "scenario.json"
    path.write_text(broken, encoding="utf-8")

    with pytest.raises(ScenarioError):
        load_scenario(path)


def test_a_missing_scenario_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ScenarioError):
        load_scenario(tmp_path / "absent.json")
