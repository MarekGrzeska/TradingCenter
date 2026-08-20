"""The model catalogue — `models_catalogue.py` and what `GET /models` publishes.

No database and no app here except where a route is the thing under test; the catalogue
is built from settings and holds no state of its own.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from teams.config import ModelCatalogueEntry
from teams.contract import ModelOut
from teams.models_catalogue import ModelCatalogue, ModelNotInCatalogue


def _entry(model_id: str, *, cost_rank: int, input_rate: str = "1", output_rate: str = "6"):
    return ModelCatalogueEntry(
        id=model_id,
        model=f"{model_id}-prod",
        display_name=model_id.title(),
        cost_rank=cost_rank,
        input_rate_per_1m=Decimal(input_rate),
        output_rate_per_1m=Decimal(output_rate),
    )


def _catalogue() -> ModelCatalogue:
    return ModelCatalogue([_entry("luna", cost_rank=2), _entry("mini", cost_rank=1)])


def test_entries_come_cheapest_first() -> None:
    # specs/teams-models: the order is the catalogue's to publish, not the terminal's to
    # work out from the rates.
    assert [entry.id for entry in _catalogue().entries()] == ["mini", "luna"]


def test_ids_are_what_a_definition_is_checked_against() -> None:
    assert _catalogue().ids() == {"luna", "mini"}


def test_a_model_outside_the_catalogue_raises_rather_than_substituting() -> None:
    with pytest.raises(ModelNotInCatalogue, match="gpt-9-imaginary"):
        _catalogue().get("gpt-9-imaginary")


def test_the_published_entry_carries_everything_a_picker_needs() -> None:
    out = ModelOut.from_entry(_entry("luna", cost_rank=2, input_rate="1.25", output_rate="10"))

    assert out.model_dump() == {
        "id": "luna",
        "display_name": "Luna",
        "cost_rank": 2,
        # Strings, in the unit they were configured in — the terminal renders these, it
        # does not compute with them.
        "input_rate_per_1m": "1.25",
        "output_rate_per_1m": "10",
    }
    # Nothing about which upstream model answers: `ModelCatalogueEntry.model` stays this
    # module's business.
    assert "model" not in out.model_dump()
