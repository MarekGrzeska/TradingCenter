"""The loop, against a scripted provider and a scripted tool server.

Neither stand-in is a mock of an interface nobody checks: `FakeProvider` yields the same
chunk types `OpenAIProvider` does, and `FakeToolServer` returns the same `ToolOutcome`
`ToolServer` does — the shapes are the module's own, and `test_tool_server.py` proves
the real client produces them against a real MCP server.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from agent.graph import TOOL_CALL_CEILING, build_graph, initial_state
from agent.provider import TextDelta, ToolCallRequest, ToolRound, UsageReport
from agent.tools import ToolDescriptor, ToolOutcome, ToolOutcomeKind

PRICE_TOOL = ToolDescriptor(
    name="get_last_price",
    description="Last price for a symbol, UTC, bid side.",
    input_schema={"type": "object", "properties": {"symbol": {"type": "string"}}},
)


class FakeProvider:
    """Each entry in `script` is one model call's chunks, in order."""

    def __init__(self, script: list[list[Any]], *, raise_on: int | None = None) -> None:
        self._script = script
        self._raise_on = raise_on
        self.calls: list[dict] = []

    async def stream(
        self,
        *,
        model: str,
        system_prompt: str,
        history: list[tuple[str, str]],
        tools: Sequence[ToolDescriptor] = (),
        rounds: Sequence[ToolRound] = (),
    ):
        index = len(self.calls)
        self.calls.append(
            {"tools": list(tools), "rounds": list(rounds), "history": list(history)}
        )
        for chunk in self._script[index]:
            yield chunk
        if self._raise_on == index:
            raise RuntimeError("provider broke")


class FakeToolServer:
    def __init__(self, outcomes: dict[str, ToolOutcome] | None = None) -> None:
        self._outcomes = outcomes or {}
        self.seen: list[tuple[str, dict]] = []

    async def call(self, name: str, arguments: dict) -> ToolOutcome:
        self.seen.append((name, arguments))
        return self._outcomes.get(
            name, ToolOutcome(ToolOutcomeKind.OK, f"{name} says 21000.5", 4)
        )


async def _run(provider, tool_server=None, *, tools=(PRICE_TOOL,)):
    seen: list[str] = []

    async def on_delta(text: str) -> None:
        seen.append(text)

    graph = build_graph(provider, tool_server)  # pyright: ignore[reportArgumentType]
    result = await graph.ainvoke(
        initial_state(
            system_prompt="be helpful",
            history=[("operator", "what is US100 at?")],
            model="luna-prod",
            on_delta=on_delta,
            tools=tools,
        )
    )
    return result, seen


async def test_a_turn_without_tool_calls_ends_after_one_model_call() -> None:
    provider = FakeProvider([[TextDelta("no need to look"), UsageReport(10, 5, None, None)]])

    result, streamed = await _run(provider, FakeToolServer())

    assert result["text"] == "no need to look"
    assert result["calls"] == []
    assert len(result["usages"]) == 1
    assert streamed == ["no need to look"]


async def test_one_tool_call_produces_two_model_calls_and_one_record() -> None:
    provider = FakeProvider(
        [
            [
                TextDelta("let me check. "),
                ToolCallRequest("c1", "get_last_price", {"symbol": "US100"}),
                UsageReport(10, 5, None, None),
            ],
            [TextDelta("21000.5, three minutes ago."), UsageReport(80, 12, None, None)],
        ]
    )
    server = FakeToolServer()

    result, streamed = await _run(provider, server)

    assert server.seen == [("get_last_price", {"symbol": "US100"})]
    # The transcript is what the operator saw, preamble included.
    assert result["text"] == "let me check. 21000.5, three minutes ago."
    assert streamed == ["let me check. ", "21000.5, three minutes ago."]
    assert len(result["usages"]) == 2
    assert [call.name for call in result["calls"]] == ["get_last_price"]
    assert result["calls"][0].outcome == "ok"
    assert result["calls"][0].round_index == 0


async def test_the_second_model_call_sees_the_round_it_asked_for() -> None:
    provider = FakeProvider(
        [
            [ToolCallRequest("c1", "get_last_price", {"symbol": "US100"}), UsageReport(1, 1, None, None)],
            [TextDelta("done"), UsageReport(1, 1, None, None)],
        ]
    )

    await _run(provider, FakeToolServer())

    assert provider.calls[0]["rounds"] == []
    replayed = provider.calls[1]["rounds"]
    assert len(replayed) == 1
    assert replayed[0].calls[0].name == "get_last_price"
    assert "21000.5" in replayed[0].results[0].text


async def test_three_calls_in_one_turn_are_recorded_in_order() -> None:
    provider = FakeProvider(
        [
            [
                ToolCallRequest("a", "list_tracked_pairs", {}),
                ToolCallRequest("b", "get_last_price", {"symbol": "US100"}),
                UsageReport(1, 1, None, None),
            ],
            [ToolCallRequest("c", "describe_coverage", {"symbol": "US100"}), UsageReport(1, 1, None, None)],
            [TextDelta("here it is"), UsageReport(1, 1, None, None)],
        ]
    )

    result, _ = await _run(provider, FakeToolServer())

    assert [call.name for call in result["calls"]] == [
        "list_tracked_pairs",
        "get_last_price",
        "describe_coverage",
    ]
    # Two rounds, and the third call belongs to the second of them.
    assert [call.round_index for call in result["calls"]] == [0, 0, 1]
    assert len(result["usages"]) == 3


async def test_a_refusal_reaches_the_model_and_the_turn_carries_on() -> None:
    provider = FakeProvider(
        [
            [ToolCallRequest("c1", "get_last_price", {"symbol": "NOPE"}), UsageReport(1, 1, None, None)],
            [ToolCallRequest("c2", "get_last_price", {"symbol": "US100"}), UsageReport(1, 1, None, None)],
            [TextDelta("21000.5"), UsageReport(1, 1, None, None)],
        ]
    )
    server = FakeToolServer(
        {
            "get_last_price": ToolOutcome(
                ToolOutcomeKind.REFUSED, "nobody collects NOPE. Call list_tracked_pairs first.", 2
            )
        }
    )

    result, _ = await _run(provider, server)

    assert result["failed"] is False
    assert result["text"] == "21000.5"
    # The server's own sentence, not a summary of it — that is what the model corrects on.
    assert "list_tracked_pairs first" in provider.calls[1]["rounds"][0].results[0].text
    assert [call.outcome for call in result["calls"]] == ["refused", "refused"]


async def test_an_unavailable_server_is_a_result_not_a_failed_turn() -> None:
    provider = FakeProvider(
        [
            [ToolCallRequest("c1", "get_last_price", {"symbol": "US100"}), UsageReport(1, 1, None, None)],
            [TextDelta("I cannot reach the archive right now."), UsageReport(1, 1, None, None)],
        ]
    )
    server = FakeToolServer(
        {
            "get_last_price": ToolOutcome(
                ToolOutcomeKind.UNAVAILABLE,
                "the tool server did not answer within 15s. The call was not made — this "
                "says nothing about the archive's own data.",
                15000,
            )
        }
    )

    result, _ = await _run(provider, server)

    assert result["failed"] is False
    assert result["calls"][0].outcome == "unavailable"
    assert "says nothing about the archive" in provider.calls[1]["rounds"][0].results[0].text


async def test_the_ceiling_stops_the_calls_and_still_gets_an_answer() -> None:
    # One call per round, forever — the shape a looping model actually has.
    asks = [
        [ToolCallRequest(f"c{i}", "get_last_price", {"symbol": "US100"}), UsageReport(1, 1, None, None)]
        for i in range(TOOL_CALL_CEILING + 2)
    ]
    provider = FakeProvider([*asks, [TextDelta("giving up"), UsageReport(1, 1, None, None)]])
    server = FakeToolServer()

    result, _ = await _run(provider, server)

    assert len(server.seen) == TOOL_CALL_CEILING
    assert len(result["calls"]) == TOOL_CALL_CEILING
    # Past the ceiling the model is offered no tools at all, so it has to answer.
    assert provider.calls[TOOL_CALL_CEILING]["tools"] == []
    assert result["text"] == "giving up"
    assert result["failed"] is False


async def test_no_tools_offered_means_the_model_is_never_asked_to_hold_any() -> None:
    provider = FakeProvider([[TextDelta("no archive today"), UsageReport(1, 1, None, None)]])

    result, _ = await _run(provider, FakeToolServer(), tools=())

    assert provider.calls[0]["tools"] == []
    assert result["calls"] == []


async def test_a_provider_failure_after_a_tool_call_keeps_the_text_and_the_record() -> None:
    provider = FakeProvider(
        [
            [ToolCallRequest("c1", "get_last_price", {"symbol": "US100"}), UsageReport(1, 1, None, None)],
            [TextDelta("it is ")],
        ],
        raise_on=1,
    )

    result, _ = await _run(provider, FakeToolServer())

    assert result["failed"] is True
    assert result["text"] == "it is "
    # The call happened and cost time; a failed turn does not un-make it.
    assert len(result["calls"]) == 1
    assert len(result["usages"]) == 2
