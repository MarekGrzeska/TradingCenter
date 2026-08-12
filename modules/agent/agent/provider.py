"""The OpenAI client — one call per round of a turn, streamed, tools optional.

This module is the one place `langchain_openai`'s message classes exist; everywhere
else in this module a turn's history is `(role, content)` pairs in this module's own
vocabulary (`"operator"` / `"agent"`), never langchain's. Tool calls widen that boundary
without moving it: `ToolCallRequest` and `ToolRound` are this module's shapes, and the
translation into and out of langchain's `tool_calls`/`ToolMessage` happens here.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_openai import ChatOpenAI

from .config import Settings
from .tools import ToolDescriptor


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class ToolCallRequest:
    """The model asking for a tool. `id` is the provider's own correlation id and has to
    travel back on the result — an answer with the wrong id is an answer to a question
    the model did not ask."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolCallResult:
    id: str
    name: str
    text: str


@dataclass(frozen=True)
class ToolRound:
    """One ask-and-answer within a turn, replayed to the provider on the next call so it
    can see what it already asked for. Lives as long as the turn and no longer
    (design.md, "Wynik narzędzia żyje jedną turę")."""

    calls: tuple[ToolCallRequest, ...]
    results: tuple[ToolCallResult, ...]


@dataclass(frozen=True)
class UsageReport:
    """`None` in any field is "the provider did not say", never zero
    (specs/agent-usage, "Zużycia, którego dostawca nie podał, MUST NOT być
    zgadywane")."""

    input_tokens: int | None
    output_tokens: int | None
    cached_tokens: int | None
    reasoning_tokens: int | None


ProviderChunk = TextDelta | ToolCallRequest | UsageReport


class ModelProvider(Protocol):
    def stream(
        self,
        *,
        model: str,
        system_prompt: str,
        history: list[tuple[str, str]],
        tools: Sequence[ToolDescriptor] = (),
        rounds: Sequence[ToolRound] = (),
    ) -> AsyncIterator[ProviderChunk]: ...


class OpenAIProvider:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _client(self, model: str, tools: Sequence[ToolDescriptor]):
        client = ChatOpenAI(
            model=model,
            api_key=self._settings.openai_api_key,  # pyright: ignore[reportArgumentType]
            streaming=True,
            # Without this the provider's usage arrives on no chunk at all when
            # streaming — the one field specs/agent-usage exists to record.
            stream_usage=True,
        )
        if not tools:
            return client
        # The schemas come from the tool server unread (specs/agent-tool-access, "Moduł
        # nie trzyma kopii tego, co ogłasza serwer narzędzi"): this module does not
        # validate arguments against a description it did not write, and a second
        # opinion here would only be a second thing to keep in step.
        return client.bind_tools(
            [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.input_schema,
                    },
                }
                for tool in tools
            ]
        )

    async def stream(
        self,
        *,
        model: str,
        system_prompt: str,
        history: list[tuple[str, str]],
        tools: Sequence[ToolDescriptor] = (),
        rounds: Sequence[ToolRound] = (),
    ) -> AsyncIterator[ProviderChunk]:
        messages: list[BaseMessage] = [SystemMessage(content=system_prompt)]
        for role, content in history:
            messages.append(
                HumanMessage(content=content) if role == "operator" else AIMessage(content=content)
            )
        for round_ in rounds:
            messages.append(
                AIMessage(
                    content="",
                    tool_calls=[
                        {"id": call.id, "name": call.name, "args": call.arguments}
                        for call in round_.calls
                    ],
                )
            )
            for result in round_.results:
                messages.append(ToolMessage(content=result.text, tool_call_id=result.id))

        client = self._client(model, tools)
        usage: dict | None = None
        # Chunks are summed rather than inspected one by one: a tool call arrives split
        # across chunks as partial JSON, and langchain's own accumulation is what turns
        # the pieces back into arguments. Text is yielded as it comes regardless — the
        # operator is watching a panel.
        accumulated: AIMessageChunk | None = None
        async for chunk in client.astream(messages):
            if not isinstance(chunk, AIMessageChunk):  # pragma: no cover - defensive
                continue
            accumulated = chunk if accumulated is None else accumulated + chunk
            if chunk.content:
                yield TextDelta(text=str(chunk.content))
            reported = getattr(chunk, "usage_metadata", None)
            if reported:
                usage = reported

        if accumulated is not None:
            for call in accumulated.tool_calls:
                yield ToolCallRequest(
                    # A provider that omits the id leaves nothing to correlate a result
                    # with; the tool name is the only stable thing left to use.
                    id=call.get("id") or call["name"],
                    name=call["name"],
                    arguments=call.get("args") or {},
                )

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
