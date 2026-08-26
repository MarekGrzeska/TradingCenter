"""The queryable catalogue built from `Settings.models`. A twin of agent's with one thing deliberately
missing: no default and no `resolve()` — every agent names its own model or the revision is refused.

What this adds over `config.py`'s own checks is a stable order and a lookup that names a refusal."""

from __future__ import annotations

from .config import ModelCatalogueEntry, Settings


class ModelNotInCatalogue(ValueError):
    """A definition named a model this module does not offer. Raised rather than quietly swapped: a run
    answered by a model the operator did not ask for cannot be compared with the one before it."""

    def __init__(self, model_id: str) -> None:
        super().__init__(f"model {model_id!r} is not in this module's catalogue")
        self.model_id = model_id


class ModelCatalogue:
    def __init__(self, entries: list[ModelCatalogueEntry]) -> None:
        self._by_id = {entry.id: entry for entry in entries}

    @classmethod
    def from_settings(cls, settings: Settings) -> ModelCatalogue:
        return cls(settings.models)

    def entries(self) -> list[ModelCatalogueEntry]:
        """Cheapest first — a wybierak needs no opinion of its own about the order
        (specs/teams-models, "porządek od najtańszego do najdroższego")."""
        return sorted(self._by_id.values(), key=lambda entry: entry.cost_rank)

    def ids(self) -> frozenset[str]:
        """What a definition's `model_id` is checked against — see `validation.py`."""
        return frozenset(self._by_id)

    def get(self, model_id: str) -> ModelCatalogueEntry:
        try:
            return self._by_id[model_id]
        except KeyError:
            raise ModelNotInCatalogue(model_id) from None
