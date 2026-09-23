"""OpenAI's succession of models, applied at every start: a session or a team revision naming a model the catalogue
no longer carries moves to its successor, once that successor is configured — so no deploy order leaves a gap."""

from __future__ import annotations

from collections.abc import Collection

SUCCESSORS: dict[str, str] = {
    "gpt-5.6-luna": "gpt-6-luna",
    "gpt-5.6-sol": "gpt-6-sol",
    # Terra has no GPT-6 successor; Sol is the entry at its price.
    "gpt-5.6-terra": "gpt-6-sol",
}


def applicable(configured: Collection[str]) -> dict[str, str]:
    """Only a retired model with its successor in place: before the operator's apply the old model is still
    configured and nothing moves; a catalogue without the successor leaves the refusal naming the old one."""
    return {
        old: new for old, new in SUCCESSORS.items() if old not in configured and new in configured
    }
