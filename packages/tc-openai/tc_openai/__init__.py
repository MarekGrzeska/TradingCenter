"""The OpenAI call, shared by the two modules that make one.

Everything worth importing is in `provider`; this re-exports it so a consumer writes
`from tc_openai import Briefing` rather than naming the submodule.
"""

from .provider import (
    Briefing,
    Conversation,
    Given,
    ModelProvider,
    OpenAIProvider,
    ProviderChunk,
    TextDelta,
    ToolCallRequest,
    ToolCallResult,
    ToolRound,
    ToolSpec,
    UsageReport,
)

__all__ = [
    "Briefing",
    "Conversation",
    "Given",
    "ModelProvider",
    "OpenAIProvider",
    "ProviderChunk",
    "TextDelta",
    "ToolCallRequest",
    "ToolCallResult",
    "ToolRound",
    "ToolSpec",
    "UsageReport",
]
