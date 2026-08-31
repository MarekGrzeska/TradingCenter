"""The OpenAI client — one call per round, streamed, tools optional. One copy of what agent's and teams' providers
each carried, 79.4% identical; the 20% that differed is now a type rather than a history-shaped argument."""

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


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class ToolCallRequest:
    """The model asking for a tool. `id` is the provider's own correlation id and has to travel back on
    the result — an answer with the wrong id answers a question the model did not ask."""

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
    """One ask-and-answer within a turn, replayed to the provider on the next call so it can see what
    it already asked for. Lives as long as the turn and no longer."""

    calls: tuple[ToolCallRequest, ...]
    results: tuple[ToolCallResult, ...]


@dataclass(frozen=True)
class UsageReport:
    """`None` in any field is "the provider did not say", never zero."""

    input_tokens: int | None
    output_tokens: int | None
    cached_tokens: int | None
    reasoning_tokens: int | None


ProviderChunk = TextDelta | ToolCallRequest | UsageReport


class ToolSpec(Protocol):
    """What the provider needs of a tool descriptor, and nothing more. Properties rather than plain
    attributes: both modules' descriptors are frozen, and a writable protocol does not accept one."""

    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str: ...

    @property
    def input_schema(self) -> dict[str, Any]: ...


@dataclass(frozen=True)
class Conversation:
    """Agent's input: the session's turns, oldest first, as `(role, content)` where role
    is this repository's own vocabulary — `"operator"` or `"agent"`, never langchain's."""

    turns: Sequence[tuple[str, str]]


@dataclass(frozen=True)
class Briefing:
    """Teams' input: one message, built for one agent. Not a one-element conversation —
    a distinct shape, so that a caller holding a briefing has nothing to append to."""

    text: str


Given = Conversation | Briefing


class ModelProvider(Protocol):
    def stream(
        self,
        *,
        model: str,
        system_prompt: str,
        given: Given,
        tools: Sequence[ToolSpec] = (),
        rounds: Sequence[ToolRound] = (),
    ) -> AsyncIterator[ProviderChunk]: ...


class OpenAIProvider:
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def _client(self, model: str, tools: Sequence[ToolSpec]):
        client = ChatOpenAI(
            model=model,
            api_key=self._api_key,  # pyright: ignore[reportArgumentType]
            streaming=True,
            # Without this the provider's usage arrives on no chunk at all when
            # streaming — the one field specs/agent-usage exists to record.
            stream_usage=True,
            # `/v1/responses`, not `/v1/chat/completions`: a reasoning model asked for function tools
            # there answers 400. The other way out buys tools by throwing the reasoning away.
            use_responses_api=True,
        )
        if not tools:
            return client
        # The schemas come from the tool server unread: this module does not validate arguments
        # against a description it did not write.
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
        given: Given,
        tools: Sequence[ToolSpec] = (),
        rounds: Sequence[ToolRound] = (),
    ) -> AsyncIterator[ProviderChunk]:
        messages: list[BaseMessage] = [SystemMessage(content=system_prompt)]
        match given:
            case Briefing(text=text):
                messages.append(HumanMessage(content=text))
            case Conversation(turns=turns):
                for role, content in turns:
                    messages.append(
                        HumanMessage(content=content)
                        if role == "operator"
                        else AIMessage(content=content)
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
        # Chunks are summed rather than inspected one by one: a tool call arrives split across chunks
        # as partial JSON, and langchain's accumulation is what turns the pieces back into arguments.
        accumulated: AIMessageChunk | None = None
        async for chunk in client.astream(messages):
            if not isinstance(chunk, AIMessageChunk):  # pragma: no cover - defensive
                continue
            accumulated = chunk if accumulated is None else accumulated + chunk
            # `.text`, not `str(.content)`: on the responses API `content` is a list of blocks, and
            # stringifying it would stream `[{'type': 'function_call', ...}]` into the panel as prose.
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
