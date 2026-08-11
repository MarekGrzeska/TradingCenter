"""The queryable catalogue built from `Settings.models` — specs/agent-models.

`config.py` already refuses to start with a model missing a rate, a duplicate id, or a
`default_model_id` outside the list — this module does not re-check any of that. What it
adds is the two things a caller actually needs: a stable sort (cheapest first) and a
lookup that turns "model spoza katalogu" into a named refusal rather than a `KeyError`.
"""

from __future__ import annotations

from .config import ModelCatalogueEntry, Settings


class ModelNotInCatalogue(ValueError):
    """A caller named a model this module does not offer.

    specs/agent-models, "Model spoza katalogu jest odmową, nie podmianą" — raised rather
    than silently falling back to the default, so a caller is never billed for a model
    it did not ask for.
    """

    def __init__(self, model_id: str) -> None:
        super().__init__(f"model {model_id!r} is not in this module's catalogue")
        self.model_id = model_id


class ModelCatalogue:
    def __init__(self, entries: list[ModelCatalogueEntry], default_model_id: str) -> None:
        self._by_id = {entry.id: entry for entry in entries}
        self.default_model_id = default_model_id

    @classmethod
    def from_settings(cls, settings: Settings) -> ModelCatalogue:
        return cls(settings.models, settings.default_model_id)

    def entries(self) -> list[ModelCatalogueEntry]:
        """Cheapest first — a wybierak needs no opinion of its own about the order."""
        return sorted(self._by_id.values(), key=lambda entry: entry.cost_rank)

    def get(self, model_id: str) -> ModelCatalogueEntry:
        try:
            return self._by_id[model_id]
        except KeyError:
            raise ModelNotInCatalogue(model_id) from None

    def resolve(self, requested: str | None) -> ModelCatalogueEntry:
        """The model a session actually gets: the one asked for, or the module's
        default when none was named (specs/agent-models, "Sesja utworzona bez
        wskazania modelu MUST dostać model domyślny modułu")."""
        return self.get(requested) if requested is not None else self.get(self.default_model_id)
