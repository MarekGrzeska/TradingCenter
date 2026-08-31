"""`stream()` — the only method either module calls, and until now the only one nothing ran. The seam is
`ChatOpenAI` itself, so message building, `bind_tools`, accumulation and the usage read all still run."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import pytest
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from tc_openai import (
    Briefing,
    Conversation,
    OpenAIProvider,
    TextDelta,
    ToolCallRequest,
    ToolCallResult,
    ToolRound,
    UsageReport,
)
from tc_openai import provider as provider_module


@dataclass(frozen=True)
class FakeTool:
    name: str
    description: str
    input_schema: dict


PRICE_TOOL = FakeTool(
    name="get_last_price",
    description="Last price for a symbol.",
    input_schema={"type": "object", "properties": {"symbol": {"type": "string"}}},
)


class _Upstream:
    """Stands in for `ChatOpenAI`: constructed like it, binds tools like it, and streams
    the chunks a test scripted — then raises, if the test scripted that too."""

    def __init__(self) -> None:
        self.chunks: list[AIMessageChunk] = []
        self.raises: Exception | None = None
        self.built: dict[str, Any] = {}
        self.bound: Any = None
        self.sent: list[Any] = []

    def __call__(self, **kwargs: Any) -> _Upstream:
        self.built = kwargs
        return self

    def bind_tools(self, tools: Any) -> _Upstream:
        self.bound = tools
        return self

    def astream(self, messages: Any) -> AsyncIterator[AIMessageChunk]:
        self.sent = list(messages)

        async def run() -> AsyncIterator[AIMessageChunk]:
            for chunk in self.chunks:
                yield chunk
            if self.raises is not None:
                raise self.raises

        return run()


@pytest.fixture
def upstream(monkeypatch: pytest.MonkeyPatch) -> _Upstream:
    fake = _Upstream()
    monkeypatch.setattr(provider_module, "ChatOpenAI", fake)
    return fake


async def _drain(provider: OpenAIProvider, **kwargs: Any) -> list[Any]:
    return [chunk async for chunk in provider.stream(**kwargs)]


async def test_a_turn_with_tools_assembles_one_call_from_its_pieces(upstream: _Upstream) -> None:
    """The arguments arrive as partial JSON split across chunks, and langchain's accumulation puts them
    back together. Read chunk by chunk the tool is called with nothing, on an argument the model did send."""
    upstream.chunks = [
        AIMessageChunk(content=[{"type": "text", "text": "checking", "index": 0}]),
        AIMessageChunk(
            content=[],
            tool_call_chunks=[
                {"name": "get_last_price", "args": '{"sym', "id": "call-1", "index": 0}
            ],
        ),
        AIMessageChunk(
            content=[],
            tool_call_chunks=[{"name": None, "args": 'bol": "GOLD"}', "id": None, "index": 0}],
            usage_metadata={
                "input_tokens": 11,
                "output_tokens": 4,
                "total_tokens": 15,
                "input_token_details": {"cache_read": 8},
                "output_token_details": {"reasoning": 3},
            },
        ),
    ]

    seen = await _drain(
        OpenAIProvider(api_key="key"),
        model="luna-prod",
        system_prompt="you are the analyst",
        given=Briefing(text="what is GOLD at?"),
        tools=[PRICE_TOOL],
    )

    assert seen == [
        TextDelta(text="checking"),
        ToolCallRequest(id="call-1", name="get_last_price", arguments={"symbol": "GOLD"}),
        UsageReport(input_tokens=11, output_tokens=4, cached_tokens=8, reasoning_tokens=3),
    ]
    # Usage arrives on no chunk at all without this, and it is the field specs/agent-usage
    # exists to record.
    assert upstream.built["stream_usage"] is True
    assert upstream.bound[0]["function"]["name"] == "get_last_price"


async def test_an_upstream_failure_reaches_the_caller_carrying_its_reason(
    upstream: _Upstream,
) -> None:
    """The incident itself. A reason that stops here is a panel saying "incomplete" about a turn whose
    cause the provider wrote down and this dropped."""
    upstream.chunks = [AIMessageChunk(content=[{"type": "text", "text": "checking", "index": 0}])]
    upstream.raises = RuntimeError(
        "Error code: 400 - Function tools with reasoning_effort are not supported"
    )

    seen: list[Any] = []
    with pytest.raises(RuntimeError, match="Function tools with reasoning_effort"):
        async for chunk in OpenAIProvider(api_key="key").stream(
            model="luna-prod",
            system_prompt="you are the analyst",
            given=Briefing(text="what is GOLD at?"),
            tools=[PRICE_TOOL],
        ):
            seen.append(chunk)

    # What the model already said is the operator's, failure or not.
    assert seen == [TextDelta(text="checking")]


async def test_a_round_is_replayed_so_the_model_sees_what_it_already_asked(
    upstream: _Upstream,
) -> None:
    """A result sent back without the call that produced it reads as an answer to nothing, and
    `tool_call_id` is what pairs the two."""
    upstream.chunks = [AIMessageChunk(content=[{"type": "text", "text": "2400", "index": 0}])]

    await _drain(
        OpenAIProvider(api_key="key"),
        model="luna-prod",
        system_prompt="you are the analyst",
        given=Conversation(turns=[("operator", "what is GOLD at?"), ("agent", "one moment")]),
        tools=[PRICE_TOOL],
        rounds=[
            ToolRound(
                calls=(
                    ToolCallRequest(
                        id="call-1", name="get_last_price", arguments={"symbol": "GOLD"}
                    ),
                ),
                results=(ToolCallResult(id="call-1", name="get_last_price", text="2400.0"),),
            )
        ],
    )

    kinds = [type(message) for message in upstream.sent]
    assert kinds == [
        SystemMessage,
        HumanMessage,  # the operator's turn
        AIMessage,  # the agent's
        AIMessage,  # the round's call, replayed
        ToolMessage,
    ]
    assert upstream.sent[3].tool_calls == [
        {"id": "call-1", "name": "get_last_price", "args": {"symbol": "GOLD"}, "type": "tool_call"}
    ]
    assert upstream.sent[4].tool_call_id == "call-1"
    assert upstream.sent[4].content == "2400.0"


async def test_usage_the_provider_never_reported_is_none_and_never_zero(
    upstream: _Upstream,
) -> None:
    """"Zużycia, którego dostawca nie podał, MUST NOT być zgadywane" — and zero is a guess that reads
    as a measurement. A turn always ends in a report, so the caller has one shape to store."""
    upstream.chunks = [AIMessageChunk(content=[{"type": "text", "text": "2400", "index": 0}])]

    seen = await _drain(
        OpenAIProvider(api_key="key"),
        model="luna-prod",
        system_prompt="you are the analyst",
        given=Briefing(text="what is GOLD at?"),
    )

    assert seen == [TextDelta(text="2400"), UsageReport(None, None, None, None)]
    # No tools, so nothing was bound — the same client serves both paths.
    assert upstream.bound is None
