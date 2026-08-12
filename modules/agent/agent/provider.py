"""The OpenAI client — one call per turn, streamed, no tools.

This module is the one place `langchain_openai`'s message classes exist; everywhere
else in this module a turn's history is `(role, content)` pairs in this module's own
vocabulary (`"operator"` / `"agent"`), never langchain's.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from .config import Settings


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
        self, *, model: str, system_prompt: str, history: list[tuple[str, str]]
    ) -> AsyncIterator[ProviderChunk]: ...


class OpenAIProvider:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _client(self, model: str) -> ChatOpenAI:
        return ChatOpenAI(
            model=model,
            api_key=self._settings.openai_api_key,  # pyright: ignore[reportArgumentType]
            streaming=True,
            # Without this the provider's usage arrives on no chunk at all when
            # streaming — the one field specs/agent-usage exists to record.
            stream_usage=True,
        )

    async def stream(
        self, *, model: str, system_prompt: str, history: list[tuple[str, str]]
    ) -> AsyncIterator[ProviderChunk]:
        messages: list[BaseMessage] = [SystemMessage(content=system_prompt)]
        for role, content in history:
            messages.append(
                HumanMessage(content=content) if role == "operator" else AIMessage(content=content)
            )
        client = self._client(model)
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
