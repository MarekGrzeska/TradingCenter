"""The Azure OpenAI client — one call per turn, streamed, no tools.

This module is the one place `langchain_openai`'s message classes exist; everywhere
else in this module a turn's history is `(role, content)` pairs in this module's own
vocabulary (`"operator"` / `"agent"`), never langchain's.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Protocol

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI

from .config import Settings

# Azure Cognitive Services' own resource id — the audience a managed-identity token must
# be issued for to call Azure OpenAI (design.md, "Wobec Azure OpenAI: tożsamość
# zarządzana, lokalnie klucz").
_COGNITIVE_SERVICES_SCOPE = "https://cognitiveservices.azure.com/.default"


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class UsageReport:
    """`None` in any field is "the provider did not say", never zero
    (specs/agent-usage, "Zużycia, którego dostawca nie podał, MUST NOT być
    zgadywane")."""

    input_tokens: int | None
    output_tokens: int | None
    cached_tokens: int | None
    reasoning_tokens: int | None


ProviderChunk = TextDelta | UsageReport


class ModelProvider(Protocol):
    def stream(
        self, *, deployment: str, system_prompt: str, history: list[tuple[str, str]]
    ) -> AsyncIterator[ProviderChunk]: ...


class AzureOpenAIProvider:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _client(self, deployment: str) -> AzureChatOpenAI:
        kwargs: dict[str, Any] = {
            "azure_endpoint": self._settings.azure_openai_endpoint,
            "api_version": self._settings.azure_openai_api_version,
            "azure_deployment": deployment,
            "streaming": True,
            # Without this the provider's usage arrives on no chunk at all when
            # streaming — the one field specs/agent-usage exists to record.
            "stream_usage": True,
        }
        if self._settings.azure_openai_api_key is not None:
            kwargs["api_key"] = self._settings.azure_openai_api_key
        else:
            # Imported lazily: this branch runs only in the managed-identity mode
            # config.py already validated, and the sync `azure.identity` (not `.aio`)
            # is what `azure_ad_token_provider` — a plain sync callable — expects.
            from azure.identity import DefaultAzureCredential, get_bearer_token_provider

            kwargs["azure_ad_token_provider"] = get_bearer_token_provider(
                DefaultAzureCredential(), _COGNITIVE_SERVICES_SCOPE
            )
        return AzureChatOpenAI(**kwargs)

    async def stream(
        self, *, deployment: str, system_prompt: str, history: list[tuple[str, str]]
    ) -> AsyncIterator[ProviderChunk]:
        messages: list[BaseMessage] = [SystemMessage(content=system_prompt)]
        for role, content in history:
            messages.append(
                HumanMessage(content=content) if role == "operator" else AIMessage(content=content)
            )
        client = self._client(deployment)
        usage: dict | None = None
        async for chunk in client.astream(messages):
            if chunk.content:
                yield TextDelta(text=str(chunk.content))
            reported = getattr(chunk, "usage_metadata", None)
            if reported:
                usage = reported
        if usage is None:
            yield UsageReport(None, None, None, None)
            return
        input_details = usage.get("input_token_details") or {}
        output_details = usage.get("output_token_details") or {}
        yield UsageReport(
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            cached_tokens=input_details.get("cache_read"),
            reasoning_tokens=output_details.get("reasoning"),
        )
