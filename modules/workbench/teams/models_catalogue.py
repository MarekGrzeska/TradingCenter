"""The queryable catalogue built from `Settings.models` — specs/teams-models.

A twin of `agent/models_catalogue.py` with one thing deliberately missing: there is no
`default_model_id` and no `resolve()`. A session falls back to a module-wide default
because a caller may create one without naming a model; a team revision may not — every
agent names its own model or the revision is refused at the moment it is saved
(specs/teams-models, "Model wybiera się osobno dla każdego agenta"). A fallback here
would be the silent substitution that spec's next requirement forbids.

`config.py` already refuses to start with a model missing a rate or a duplicate id, so
none of that is re-checked here. What this adds is a stable order (cheapest first) and a
lookup that turns an unknown model into a named refusal rather than a `KeyError`.
"""

from __future__ import annotations

from .config import ModelCatalogueEntry, Settings


class ModelNotInCatalogue(ValueError):
    """A definition named a model this module does not offer.

    specs/teams-models, "Model spoza katalogu jest odmową, nie podmianą" — raised rather
    than quietly swapped for something else, because a run answered by a model the
    operator did not ask for is a run that cannot be compared with the one before it.
    """

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
