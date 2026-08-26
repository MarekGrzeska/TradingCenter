"""This module's binding of `tc_openai` — the shared OpenAI call. What stays here is the pair the package
must not hold: this module's own API key, and the `Briefing` shape it calls with, because an agent sees
its predecessors' conclusions and never the run's history.

agent and teams spend against separate keys on purpose, which is why the package takes a string."""

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
