"""Steps beside agents in a revision (`teams-steps`): the shape the contract holds, the recipe check at save time, and the
catalogue as published. The recipe's own behaviour is `test_strategy_execute.py`."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from teams.contract import TeamDefinition
from teams.routers import recipes
from teams.steps import parse_params
from teams.tools import AnnouncedSnapshot
from teams.validation import DefinitionRefused, check_definition

MODELS = ("gpt-6-luna",)
RECIPE_TOOLS = (
    "strategy_signal",
    "get_positions",
    "get_working_orders",
    "get_balance",
    "size_for_margin",
    "place_order",
    "close_position",
    "get_last_price",
    "get_candles",
)


def _agent(key: str, **overrides) -> dict:
    return {"key": key, "role": "reporter", "prompt": "tell the operator", "model_id": "gpt-6-luna", **overrides}


def _step(key: str = "execute", **params) -> dict:
    return {
        "key": key,
        "recipe": "strategy_execute",
        "params": {"strategy_id": 5, "revision": 1, "symbol": "US100", **params},
    }


def _announced(*extra: str) -> AnnouncedSnapshot:
    return AnnouncedSnapshot(
        by_name={name: ["source"] for name in (*RECIPE_TOOLS, *extra)}, unreachable=[]
    )


def test_a_revision_saved_before_steps_reads_with_none() -> None:
    definition = TeamDefinition.model_validate({"agents": [_agent("solo")], "edges": []})
    assert definition.steps == []
    assert definition.node_keys() == ["solo"]


def test_a_mixed_team_wires_a_step_to_an_agent() -> None:
    definition = TeamDefinition.model_validate(
        {"agents": [_agent("reporter")], "steps": [_step()], "edges": [{"from": "execute", "to": "reporter"}]}
    )
    check_definition(definition, model_ids=MODELS, announced=_announced())


def test_a_team_of_one_step_needs_no_agent() -> None:
    TeamDefinition.model_validate({"steps": [_step()]})


@pytest.mark.parametrize(
    ("definition", "message"),
    [
        pytest.param({"agents": [], "steps": []}, "at least one agent or step", id="no node"),
        pytest.param(
            {"agents": [_agent("execute")], "steps": [_step()]}, "duplicate agent keys", id="key shared"
        ),
    ],
)
def test_shape_refusals(definition: dict, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        TeamDefinition.model_validate(definition)


@pytest.mark.parametrize(
    ("step", "message"),
    [
        pytest.param({"key": "execute", "recipe": "teleport", "params": {}}, "unknown recipe 'teleport'", id="recipe"),
        pytest.param(_step(colour="red"), "parameter 'colour'", id="extra param"),
        pytest.param({"key": "execute", "recipe": "strategy_execute", "params": {}}, "parameter", id="missing"),
        pytest.param(_step(deposit_fraction="1.5"), "deposit_fraction", id="fraction over one"),
        pytest.param(_step(deposit_fraction=True), "deposit_fraction", id="fraction not a number"),
    ],
)
def test_a_step_that_does_not_fit_its_recipe_is_refused_naming_the_step(step: dict, message: str) -> None:
    definition = TeamDefinition.model_validate({"steps": [step]})
    with pytest.raises(DefinitionRefused, match=f"step 'execute'.*{message}"):
        check_definition(definition, model_ids=MODELS, announced=_announced())


@pytest.mark.parametrize("fraction", ["0.35", 0.35])
def test_a_deposit_fraction_is_taken_as_text_or_as_the_number_the_catalogue_calls_decimal(fraction) -> None:
    definition = TeamDefinition.model_validate({"steps": [_step(deposit_fraction=fraction)]})
    check_definition(definition, model_ids=MODELS, announced=_announced())
    assert parse_params("strategy_execute", definition.steps[0].params).deposit_fraction == "0.35"  # type: ignore[attr-defined]


def test_a_recipe_tool_nobody_announces_is_refused_naming_the_step() -> None:
    definition = TeamDefinition.model_validate({"steps": [_step()]})
    announced = AnnouncedSnapshot(by_name={"strategy_signal": ["source"]}, unreachable=[])
    with pytest.raises(DefinitionRefused, match="step 'execute' is assigned tool"):
        check_definition(definition, model_ids=MODELS, announced=announced)


def test_a_fallback_notice_without_the_send_tool_is_refused() -> None:
    reporter = _agent("reporter", fallback_notice={"destination": "operator"})
    definition = TeamDefinition.model_validate({"agents": [reporter]})
    with pytest.raises(DefinitionRefused, match="agent 'reporter'.*send_telegram_message"):
        check_definition(definition, model_ids=MODELS, announced=_announced())


def test_the_catalogue_publishes_strategy_execute_with_its_parameters() -> None:
    app = FastAPI()
    app.include_router(recipes.router, prefix="/teams")
    published = TestClient(app).get("/teams/step-recipes").json()

    recipe = next(entry for entry in published if entry["name"] == "strategy_execute")
    params = {param["name"]: param for param in recipe["params"]}
    assert params["strategy_id"]["required"] is True
    assert params["deposit_fraction"]["required"] is False
    assert "place_order" in recipe["tools"]
