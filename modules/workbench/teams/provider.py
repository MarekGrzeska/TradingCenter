"""This module's binding of `tc_openai` — the shared OpenAI call.

The call itself, its streaming, its tool round-trip and the shapes below are one copy in
the package. What stays here is the pair the package must not hold: **this module's own
API key**, and the input shape it calls with — a `Briefing`, because an agent in a team sees its
predecessors' conclusions and never the run's history (specs/teams-runs, "Agent widzi
wypowiedzi poprzedników, a nie całą historię przebiegu").

agent and teams spend against separate keys on purpose — `openai-api-key` and
`teams-openai-api-key` are two secrets in Key Vault, so the experiments' cost has its own
line — which is why the package takes a string and each module supplies its own.
"""

from __future__ import annotations

from tc_openai import (
    Briefing,
    ModelProvider,
    ProviderChunk,
    TextDelta,
    ToolCallRequest,
    ToolCallResult,
    ToolRound,
    UsageReport,
)
from tc_openai import OpenAIProvider as _SharedProvider

from .config import Settings

__all__ = [
    "Briefing",
    "ModelProvider",
    "OpenAIProvider",
    "ProviderChunk",
    "TextDelta",
    "ToolCallRequest",
    "ToolCallResult",
    "ToolRound",
    "UsageReport",
]


class OpenAIProvider(_SharedProvider):
    """The shared provider, holding this module's key and nothing else."""

    def __init__(self, settings: Settings) -> None:
        super().__init__(api_key=settings.openai_api_key)
