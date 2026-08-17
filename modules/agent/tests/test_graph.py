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
from agent.models import RecordedCall
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
            {
                "tools": list(tools),
                "rounds": list(rounds),
                "history": list(history),
                "system_prompt": system_prompt,
            }
        )
        for chunk in self._script[index]:
            yield chunk
        if self._raise_on == index:
            raise RuntimeError("provider broke")


class FakeToolServer:
    def __init__(
        self,
        outcomes: dict[str, ToolOutcome] | None = None,
        account_tools: frozenset[str] = frozenset(),
    ) -> None:
        self._outcomes = outcomes or {}
        self._account_tools = account_tools
        self.seen: list[tuple[str, dict]] = []
        self.tokens: list[str | None] = []

    def moves_the_account(self, name: str) -> bool:
        return name in self._account_tools

    async def call(
        self, name: str, arguments: dict, operator_token: str | None = None
    ) -> ToolOutcome:
        # The token is accepted and recorded rather than ignored: the graph forwards it,
        # and a fake that could not take it would let that forwarding rot unnoticed.
        self.seen.append((name, arguments))
        self.tokens.append(operator_token)
        return self._outcomes.get(
            name, ToolOutcome(ToolOutcomeKind.OK, f"{name} says 21000.5", 4)
        )


class RecordingAccountTrace:
    """The trace the graph writes for a call that can move the account, without a database.

    `settled` holds only the rows that were settled, so a test can tell "written and then
    answered for" from "written and left as it was" — the difference the whole mechanism
    exists to keep (specs/agent-trading).
    """

    def __init__(self, *, fails_to_begin: bool = False) -> None:
        self.begun: list[tuple[int, int, str, dict]] = []
        self.settled: list[tuple[int, str]] = []
        self._fails = fails_to_begin

    async def begin(self, *, round_index: int, position: int, name: str, arguments: dict) -> int:
        if self._fails:
            raise RuntimeError("the database is gone")
        self.begun.append((round_index, position, name, arguments))
        return len(self.begun)

    async def settle(self, *, row_id: int, outcome: str, text: str, duration_ms: int) -> None:
        self.settled.append((row_id, outcome))


async def _run(
    provider,
    tool_server=None,
    *,
    tools=(PRICE_TOOL,),
    announced=None,
    local_tools=None,
    account_trace=None,
):
    """`announced` collects `(call, position)` for every tool call the graph announced —
    the events a caller watching the turn sees, as opposed to `result["calls"]`, which is
    what the turn hands back at the end. A test passing a list is asking about the first;
    every other test is asking about the second."""
    seen: list[str] = []
    announced_here: list[tuple[RecordedCall, int]] = announced if announced is not None else []

    async def on_delta(text: str) -> None:
        seen.append(text)

    async def on_tool_call(call: RecordedCall, position: int) -> None:
        announced_here.append((call, position))

    graph = build_graph(provider, tool_server, local_tools, None, account_trace)  # pyright: ignore[reportArgumentType]
    result = await graph.ainvoke(
        initial_state(
            system_prompt="be helpful",
            history=[("operator", "what is US100 at?")],
            model="luna-prod",
            on_delta=on_delta,
            on_tool_call=on_tool_call,
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


async def test_every_call_is_announced_as_it_resolves() -> None:
    """The graph's own half of "Wywołanie narzędzia dociera w trakcie tury": three calls
    reach the listener as three announcements, in the order they resolved, each carrying
    the position `store.record_tool_calls` will write for it."""
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
    announced: list[tuple[RecordedCall, int]] = []

    result, _ = await _run(provider, FakeToolServer(), announced=announced)

    assert [call.name for call, _position in announced] == [
        "list_tracked_pairs",
        "get_last_price",
        "describe_coverage",
    ]
    # Position restarts with the round, exactly as the store numbers it.
    assert [(call.round_index, position) for call, position in announced] == [(0, 0), (0, 1), (1, 0)]
    # What was announced is what the turn hands back — one is not a summary of the other.
    assert [call for call, _position in announced] == result["calls"]


async def test_a_refused_call_is_announced_like_any_other() -> None:
    provider = FakeProvider(
        [
            [ToolCallRequest("c1", "get_last_price", {"symbol": "NOPE"}), UsageReport(1, 1, None, None)],
            [TextDelta("that pair is not tracked"), UsageReport(1, 1, None, None)],
        ]
    )
    server = FakeToolServer(
        {"get_last_price": ToolOutcome(ToolOutcomeKind.REFUSED, "no such pair: NOPE", 3)}
    )
    announced: list[tuple[RecordedCall, int]] = []

    await _run(provider, server, announced=announced)

    assert len(announced) == 1
    call, _position = announced[0]
    assert call.outcome == str(ToolOutcomeKind.REFUSED)
    assert call.text == "no such pair: NOPE"


async def test_a_call_stopped_by_the_ceiling_is_never_announced() -> None:
    """Nothing was asked of the server, so nothing happened to show. An event here would
    put a call in the operator's panel that never left the module."""
    asks = [
        [ToolCallRequest(f"c{i}", "get_last_price", {"symbol": "US100"}), UsageReport(1, 1, None, None)]
        for i in range(TOOL_CALL_CEILING + 2)
    ]
    provider = FakeProvider([*asks, [TextDelta("giving up"), UsageReport(1, 1, None, None)]])
    announced: list[tuple[RecordedCall, int]] = []

    await _run(provider, FakeToolServer(), announced=announced)

    assert len(announced) == TOOL_CALL_CEILING


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


# --- tools this module runs itself ---------------------------------------------------

CHART_TOOL = ToolDescriptor(
    name="set_chart",
    description="Set what the operator's chart shows.",
    input_schema={"type": "object", "properties": {"symbol": {"type": "string"}}},
)


class RecordingLocalTool:
    """Stands in for `ChartTool.call` already bound to its session."""

    def __init__(self, outcome: ToolOutcome | None = None) -> None:
        self.seen: list[dict] = []
        self._outcome = outcome or ToolOutcome(ToolOutcomeKind.OK, "chart set", 2)

    async def __call__(self, arguments: dict) -> ToolOutcome:
        self.seen.append(arguments)
        return self._outcome


async def test_a_local_tool_runs_here_and_never_reaches_the_server() -> None:
    chart = RecordingLocalTool()
    provider = FakeProvider(
        [
            [ToolCallRequest("c1", "set_chart", {"symbol": "US100"}), UsageReport(1, 1, None, None)],
            [TextDelta("shown"), UsageReport(1, 1, None, None)],
        ]
    )
    server = FakeToolServer()

    result, _ = await _run(
        provider,
        server,
        tools=(PRICE_TOOL, CHART_TOOL),
        local_tools={"set_chart": chart},
    )

    assert chart.seen == [{"symbol": "US100"}]
    assert server.seen == []
    # One trace, the same shape as any other call, so the panel does not have to know
    # which tools this module owns to show what happened.
    [call] = result["calls"]
    assert (call.name, call.outcome, call.text) == ("set_chart", "ok", "chart set")


async def test_both_kinds_of_tool_share_one_turn_and_one_ceiling() -> None:
    chart = RecordingLocalTool()
    provider = FakeProvider(
        [
            [ToolCallRequest("c1", "get_last_price", {"symbol": "US100"}), UsageReport(1, 1, None, None)],
            [ToolCallRequest("c2", "set_chart", {"symbol": "US100"}), UsageReport(1, 1, None, None)],
            [TextDelta("done"), UsageReport(1, 1, None, None)],
        ]
    )
    server = FakeToolServer()

    result, _ = await _run(
        provider,
        server,
        tools=(PRICE_TOOL, CHART_TOOL),
        local_tools={"set_chart": chart},
    )

    assert [call.name for call in result["calls"]] == ["get_last_price", "set_chart"]
    assert result["tool_calls_made"] == 2
    assert result["failed"] is False


async def test_a_local_tool_refusing_is_a_result_the_model_can_act_on() -> None:
    chart = RecordingLocalTool(
        ToolOutcome(ToolOutcomeKind.REFUSED, "'TSLA' is not collected by the archive.", 1)
    )
    provider = FakeProvider(
        [
            [ToolCallRequest("c1", "set_chart", {"symbol": "TSLA"}), UsageReport(1, 1, None, None)],
            [ToolCallRequest("c2", "set_chart", {"symbol": "US100"}), UsageReport(1, 1, None, None)],
            [TextDelta("shown instead"), UsageReport(1, 1, None, None)],
        ]
    )

    result, _ = await _run(
        provider,
        FakeToolServer(),
        tools=(CHART_TOOL,),
        local_tools={"set_chart": chart},
    )

    # The refusal came back as a round result, so the model got to try again inside the
    # same turn (specs/agent-tools, "Odmowa narzędzia jest wynikiem, nie awarią tury").
    assert [call.outcome for call in result["calls"]] == ["refused", "refused"]
    assert result["failed"] is False
    assert result["text"] == "shown instead"
    assert result["rounds"][0].results[0].text.startswith("'TSLA' is not collected")


class RaisingLocalTool:
    """A local tool broken the way `ChartTool.call` can be — a database gone away, not
    a refusal it wrote itself."""

    async def __call__(self, arguments: dict) -> ToolOutcome:
        raise RuntimeError("connection reset")


async def test_a_local_tool_that_raises_is_a_result_not_a_failed_turn() -> None:
    """Mirrors `tool_server.call`'s own guard: a local tool breaking must not escape the
    round the way an unguarded exception would, taking the whole turn's text with it."""
    provider = FakeProvider(
        [
            [ToolCallRequest("c1", "set_chart", {"symbol": "US100"}), UsageReport(1, 1, None, None)],
            [TextDelta("could not set it, but here is what I know"), UsageReport(1, 1, None, None)],
        ]
    )

    result, _ = await _run(
        provider,
        FakeToolServer(),
        tools=(CHART_TOOL,),
        local_tools={"set_chart": RaisingLocalTool()},
    )

    assert result["failed"] is False
    assert result["text"] == "could not set it, but here is what I know"
    [call] = result["calls"]
    assert call.outcome == "unavailable"
    assert "connection reset" in call.text


# --- ślad wywołań ruszających rachunek (specs/agent-trading) ---

ORDER_TOOL = ToolDescriptor(
    name="place_order",
    description="Sends an order.",
    input_schema={"type": "object", "properties": {"symbol": {"type": "string"}}},
    read_only=False,
)


def _one_order(name: str = "place_order") -> FakeProvider:
    return FakeProvider(
        [
            [ToolCallRequest("o1", name, {"symbol": "US100"}), UsageReport(1, 1, None, None)],
            [TextDelta("sent"), UsageReport(1, 1, None, None)],
        ]
    )


async def test_an_order_is_traced_before_it_is_sent_and_settled_after() -> None:
    trace = RecordingAccountTrace()
    server = FakeToolServer(account_tools=frozenset({"place_order"}))

    result, _ = await _run(
        _one_order(), server, tools=(ORDER_TOOL,), account_trace=trace
    )

    assert trace.begun == [(0, 0, "place_order", {"symbol": "US100"})]
    assert trace.settled == [(1, "ok")]
    # The row the graph wrote travels back on the call, so the turn joins it to the reply
    # instead of inserting a second one.
    [call] = result["calls"]
    assert call.row_id == 1


async def test_a_read_gets_no_trace_of_its_own() -> None:
    trace = RecordingAccountTrace()
    server = FakeToolServer(account_tools=frozenset({"place_order"}))

    result, _ = await _run(
        _one_order("get_last_price"), server, account_trace=trace
    )

    assert trace.begun == []
    [call] = result["calls"]
    assert call.row_id is None


async def test_an_order_whose_trace_cannot_be_written_is_not_sent() -> None:
    """A call that moves the account is never sent without a record of it. The model is
    told, the turn carries on, and the server is not asked."""
    trace = RecordingAccountTrace(fails_to_begin=True)
    server = FakeToolServer(account_tools=frozenset({"place_order"}))

    result, _ = await _run(
        _one_order(), server, tools=(ORDER_TOOL,), account_trace=trace
    )

    assert server.seen == []
    assert result["failed"] is False
    [call] = result["calls"]
    assert call.outcome == "unavailable"
    assert call.row_id is None
    assert "was not sent" in call.text


async def test_without_a_trace_at_all_the_graph_still_runs_orders() -> None:
    """`account_trace` is optional, and a graph built without one is the shape every test
    written before this mechanism existed still uses."""
    server = FakeToolServer(account_tools=frozenset({"place_order"}))

    result, _ = await _run(_one_order(), server, tools=(ORDER_TOOL,))

    assert server.seen == [("place_order", {"symbol": "US100"})]
    [call] = result["calls"]
    assert call.row_id is None
