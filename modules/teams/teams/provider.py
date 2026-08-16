"""The OpenAI client — one call per round of one agent's work, streamed, tools optional.

`agent/provider.py`'s twin, copied rather than shared, with one shape changed on purpose.
There, a call carries a *conversation*: `(role, content)` pairs going back as far as the
session does. Here it carries a **briefing** — one message, built for this agent out of
what its predecessors handed over (specs/teams-runs, "Agent widzi wypowiedzi
poprzedników, a nie całą historię przebiegu"). A team has no transcript to replay, and a
`history` parameter here would be an invitation to grow one.

This module is the one place `langchain_openai`'s message classes exist. Everything past
it speaks this module's own shapes.
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
    travel back on the result — an answer with the wrong id is an answer to a question the
    model did not ask."""

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
    """One ask-and-answer within one agent's work, replayed to the provider on the next
    call so it can see what it already asked for. Lives as long as that agent's own loop
    and no longer — a successor is given its predecessor's *conclusion*, never the rounds
    it took to reach it."""

    calls: tuple[ToolCallRequest, ...]
    results: tuple[ToolCallResult, ...]


@dataclass(frozen=True)
class UsageReport:
    """`None` in any field is "the provider did not say", never zero (specs/teams-usage,
    "Brak informacji o zużyciu jest zapisany jako brak, nie jako zero")."""

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
        briefing: str,
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
            # Without this the provider's usage arrives on no chunk at all when streaming
            # — the one field specs/teams-usage exists to record.
            stream_usage=True,
            # `/v1/responses`, not `/v1/chat/completions`. Measured by `agent` before this
            # module existed: a reasoning model asked for function tools on
            # chat/completions answers
            #
            #   400 Function tools with reasoning_effort are not supported for <model> in
            #   /v1/chat/completions. To use function tools, use /v1/responses or set
            #   reasoning_effort to 'none'.
            #
            # The other way out of that error throws away the reasoning these models are
            # picked for. Set for every call, tools or not, so one code path serves both.
            use_responses_api=True,
        )
        if not tools:
            return client
        # The schemas come from the tool server unread (specs/teams-tool-access, "Moduł
        # nie trzyma kopii tego, co ogłasza serwer narzędzi").
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
        briefing: str,
        tools: Sequence[ToolDescriptor] = (),
        rounds: Sequence[ToolRound] = (),
    ) -> AsyncIterator[ProviderChunk]:
        messages: list[BaseMessage] = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=briefing),
        ]
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
        # the pieces back into arguments.
        accumulated: AIMessageChunk | None = None
        async for chunk in client.astream(messages):
            if not isinstance(chunk, AIMessageChunk):  # pragma: no cover - defensive
                continue
            accumulated = chunk if accumulated is None else accumulated + chunk
            # `.text`, not `str(.content)`. On the responses API `content` is a list of
            # blocks — a tool call arrives as one — and stringifying it would put
            # `[{'type': 'function_call', ...}]` into an agent's answer as prose.
            if chunk.text:
                yield TextDelta(text=chunk.text)
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
