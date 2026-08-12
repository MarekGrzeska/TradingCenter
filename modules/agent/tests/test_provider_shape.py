"""Two things about the OpenAI client that are invisible until a live call.

Both were found by one: a real turn with tools answered `400`, and the panel showed
"incomplete — broke off" with no reason recorded anywhere. These are unit assertions on
the shape, standing in for a call this suite will never make.
"""

from __future__ import annotations

from decimal import Decimal

from langchain_core.messages import AIMessageChunk

from agent.config import ModelCatalogueEntry, Settings
from agent.provider import OpenAIProvider
from agent.tools import ToolDescriptor

ONE_MODEL = [
    {
        "id": "gpt-5.6-luna",
        "model": "luna-prod",
        "display_name": "Luna",
        "cost_rank": 1,
        "input_rate_per_1m": "1",
        "output_rate_per_1m": "6",
    }
]

LUNA = ModelCatalogueEntry(
    id="gpt-5.6-luna",
    model="luna-prod",
    display_name="Luna",
    cost_rank=1,
    input_rate_per_1m=Decimal(1),
    output_rate_per_1m=Decimal(6),
)

PRICE_TOOL = ToolDescriptor(
    name="get_last_price",
    description="Last price for a symbol.",
    input_schema={"type": "object", "properties": {"symbol": {"type": "string"}}},
)


def _provider() -> OpenAIProvider:
    return OpenAIProvider(
        Settings(
            database_url="postgresql://localhost:5432/agent",
            openai_api_key="key",
            models=ONE_MODEL,
            default_model_id="gpt-5.6-luna",
            _env_file=None,  # type: ignore[call-arg]
        )
    )


def test_the_client_talks_to_the_responses_api() -> None:
    """A reasoning model asked for function tools on /v1/chat/completions answers 400:
    "Function tools with reasoning_effort are not supported ... use /v1/responses or set
    reasoning_effort to 'none'." The second way out buys tools by throwing away the
    reasoning the model was chosen for, so this is the first."""
    client = _provider()._client(LUNA.model, [])

    assert client.use_responses_api is True  # pyright: ignore[reportAttributeAccessIssue]


def test_the_responses_api_shape_stays_bound_when_tools_are_added() -> None:
    bound = _provider()._client(LUNA.model, [PRICE_TOOL])

    # bind_tools returns a Runnable wrapping the client; the setting has to survive it,
    # since the tools path is the one that needs it.
    assert bound.bound.use_responses_api is True  # pyright: ignore[reportAttributeAccessIssue]
    assert bound.kwargs["tools"][0]["function"]["name"] == "get_last_price"


def test_text_is_taken_from_blocks_not_from_stringified_content() -> None:
    """On the responses API `content` is a list of blocks and a tool call is one of
    them. `str(content)` would stream `[{'type': 'function_call', ...}]` into the
    operator's panel as prose; `.text` takes the text blocks and nothing else."""
    tool_call_chunk = AIMessageChunk(
        content=[{"type": "function_call", "name": "get_last_price", "arguments": "", "index": 0}]
    )
    text_chunk = AIMessageChunk(content=[{"type": "text", "text": "hello", "index": 0}])

    assert tool_call_chunk.text == ""
    assert text_chunk.text == "hello"
    # The older shape still reads the same way, so one branch serves both.
    assert AIMessageChunk(content="hello").text == "hello"
