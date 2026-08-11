from __future__ import annotations

from decimal import Decimal

import pytest

from agent.config import ModelCatalogueEntry
from agent.models_catalogue import ModelCatalogue, ModelNotInCatalogue

LUNA = ModelCatalogueEntry(
    id="gpt-5.6-luna",
    deployment="luna-prod",
    display_name="Luna",
    cost_rank=1,
    input_rate_per_1k=Decimal("0.0002"),
    output_rate_per_1k=Decimal("0.0012"),
)
SOL = ModelCatalogueEntry(
    id="gpt-5.6-sol",
    deployment="sol-prod",
    display_name="Sol",
    cost_rank=3,
    input_rate_per_1k=Decimal("0.005"),
    output_rate_per_1k=Decimal("0.03"),
)


def catalogue() -> ModelCatalogue:
    # Deliberately built out of cost order — entries() must sort, not echo input order.
    return ModelCatalogue([SOL, LUNA], default_model_id="gpt-5.6-luna")


def test_entries_are_sorted_cheapest_first() -> None:
    assert [e.id for e in catalogue().entries()] == ["gpt-5.6-luna", "gpt-5.6-sol"]


def test_get_returns_the_matching_entry() -> None:
    assert catalogue().get("gpt-5.6-sol") is SOL


def test_get_an_unknown_model_names_it_in_the_refusal() -> None:
    # specs/agent-models, "Model spoza katalogu jest odmową, nie podmianą"
    with pytest.raises(ModelNotInCatalogue) as err:
        catalogue().get("gpt-5.6-does-not-exist")
    assert err.value.model_id == "gpt-5.6-does-not-exist"
    assert "gpt-5.6-does-not-exist" in str(err.value)


def test_resolve_with_no_request_falls_back_to_the_default() -> None:
    # specs/agent-models, "Sesja utworzona bez wskazania modelu MUST dostać model domyślny"
    assert catalogue().resolve(None) is LUNA


def test_resolve_with_a_known_request_returns_it() -> None:
    assert catalogue().resolve("gpt-5.6-sol") is SOL


def test_resolve_with_an_unknown_request_refuses_rather_than_falling_back() -> None:
    # The whole point of specs/agent-models' "nie podmianą": an unknown request must
    # never silently execute on the default instead.
    with pytest.raises(ModelNotInCatalogue):
        catalogue().resolve("gpt-5.6-does-not-exist")


def test_a_model_retired_from_the_catalogue_is_still_a_named_refusal() -> None:
    only_sol = ModelCatalogue([SOL], default_model_id="gpt-5.6-sol")
    with pytest.raises(ModelNotInCatalogue):
        only_sol.get("gpt-5.6-luna")
