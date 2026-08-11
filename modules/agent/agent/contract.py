"""The shapes this module answers with — snake_case on the wire, same convention as
`market_data/contract.py`. Not generated: this module's contract is hand-written on both
sides rather than wired into `pnpm contract:generate`, which is market-data's alone
(design.md, "Kontrakt terminala pisany ręcznie, bez generatora").
"""

from __future__ import annotations

from pydantic import BaseModel

from .models_catalogue import ModelCatalogueEntry


class ModelOut(BaseModel):
    id: str
    display_name: str
    cost_rank: int
    # Strings, not numbers: a rate like 0.0002 round-trips exactly as text, and nothing
    # here ever sums these on the wire — the terminal reads them to render, never to
    # compute (design.md, "terminal niczego nie przelicza").
    input_rate_per_1k: str
    output_rate_per_1k: str

    @classmethod
    def from_entry(cls, entry: ModelCatalogueEntry) -> ModelOut:
        return cls(
            id=entry.id,
            display_name=entry.display_name,
            cost_rank=entry.cost_rank,
            input_rate_per_1k=str(entry.input_rate_per_1k),
            output_rate_per_1k=str(entry.output_rate_per_1k),
        )
