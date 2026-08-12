"""What a turn leaves behind besides its reply: one row per tool call, and one usage
row per model call.

Both hang off the same agent message, and neither is a message. That is the whole point
of the split — `agent/contract.py` does not change, so the terminal reads exactly the
transcript it read before this change (specs/agent-tools, "Wywołanie narzędzia zostawia
ślad").
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from agent import store
from agent.config import ModelCatalogueEntry
from agent.models import RecordedCall
from agent.prompt import SYSTEM_PROMPT_WITH_TOOLS, SYSTEM_PROMPT_WITHOUT_TOOLS
from agent.provider import TextDelta, ToolCallRequest, UsageReport
from agent.tools import ToolOutcome, ToolOutcomeKind
from agent.turn import run_turn

from .test_graph import PRICE_TOOL, FakeProvider, FakeToolServer

pytestmark = pytest.mark.db

LUNA = ModelCatalogueEntry(
    id="gpt-5.6-luna",
    model="luna-prod",
    display_name="Luna",
    cost_rank=1,
    input_rate_per_1m=Decimal(1),
    output_rate_per_1m=Decimal(6),
)


class RecordingQueue:
    def __init__(self) -> None:
        self.events: list = []

    def put_nowait(self, event) -> None:
        self.events.append(event)


class ServerWithTools(FakeToolServer):
    """A tool server the turn can also ask for a tool list — `run_turn` reads one before
    the first model call."""

    async def list_tools(self):
        return [PRICE_TOOL]


async def _new_session(conn) -> int:
    session = await store.create_session(conn, owner_principal="op-1", model_id=LUNA.id)
    await store.append_operator_message(conn, session_id=session.id, content="what is US100 at?")
    return session.id


async def test_three_calls_leave_three_rows_in_a_recoverable_order(pool, db) -> None:
    session_id = await _new_session(db)
    provider = FakeProvider(
        [
            [
                ToolCallRequest("a", "list_tracked_pairs", {}),
                ToolCallRequest("b", "get_last_price", {"symbol": "US100"}),
                UsageReport(10, 5, None, None),
            ],
            [
                ToolCallRequest("c", "describe_coverage", {"symbol": "US100"}),
                UsageReport(20, 5, None, None),
            ],
            [TextDelta("21000.5"), UsageReport(40, 8, None, None)],
        ]
    )

    await run_turn(
        pool,
        session_id=session_id,
        model_entry=LUNA,
        provider=provider,
        queue=RecordingQueue(),
        tool_server=ServerWithTools(),  # pyright: ignore[reportArgumentType]
    )

    messages = await store.get_messages(db, session_id=session_id)
    reply = messages[-1]
    calls = await store.get_tool_calls(db, message_id=reply.id)

    assert [call.tool_name for call in calls] == [
        "list_tracked_pairs",
        "get_last_price",
        "describe_coverage",
    ]
    # Order does not lean on the clock: three calls land in the same millisecond, and
    # two of them share a round.
    assert [(call.round_index, call.position) for call in calls] == [(0, 0), (0, 1), (1, 0)]
    assert calls[1].arguments == {"symbol": "US100"}
    assert all(call.outcome == "ok" for call in calls)
    assert all(call.duration_ms >= 0 for call in calls)


async def test_a_refused_call_is_recorded_with_its_reason(pool, db) -> None:
    session_id = await _new_session(db)
    provider = FakeProvider(
        [
            [
                ToolCallRequest("a", "get_last_price", {"symbol": "NOPE"}),
                UsageReport(10, 5, None, None),
            ],
            [TextDelta("nobody collects that"), UsageReport(20, 5, None, None)],
        ]
    )
    server = ServerWithTools(
        {
            "get_last_price": ToolOutcome(
                ToolOutcomeKind.REFUSED, "nobody collects NOPE. Call list_tracked_pairs first.", 3
            )
        }
    )

    await run_turn(
        pool,
        session_id=session_id,
        model_entry=LUNA,
        provider=provider,
        queue=RecordingQueue(),
        tool_server=server,  # pyright: ignore[reportArgumentType]
    )

    messages = await store.get_messages(db, session_id=session_id)
    calls = await store.get_tool_calls(db, message_id=messages[-1].id)

    assert len(calls) == 1
    assert calls[0].outcome == "refused"
    assert "list_tracked_pairs first" in calls[0].result_text


async def test_an_incomplete_turn_still_records_what_it_managed(pool, db) -> None:
    session_id = await _new_session(db)
    provider = FakeProvider(
        [
            [
                ToolCallRequest("a", "get_last_price", {"symbol": "US100"}),
                UsageReport(10, 5, None, None),
            ],
            [TextDelta("it is ")],
        ],
        raise_on=1,
    )

    await run_turn(
        pool,
        session_id=session_id,
        model_entry=LUNA,
        provider=provider,
        queue=RecordingQueue(),
        tool_server=ServerWithTools(),  # pyright: ignore[reportArgumentType]
    )

    messages = await store.get_messages(db, session_id=session_id)
    reply = messages[-1]
    assert reply.incomplete is True
    assert reply.content == "it is "
    # The call happened and cost time on both sides; a turn that broke afterwards does
    # not un-make it.
    assert len(await store.get_tool_calls(db, message_id=reply.id)) == 1


async def test_two_model_calls_leave_two_usage_rows_under_one_reply(pool, db) -> None:
    session_id = await _new_session(db)
    provider = FakeProvider(
        [
            [
                ToolCallRequest("a", "get_last_price", {"symbol": "US100"}),
                UsageReport(1_000_000, 0, None, None),
            ],
            [TextDelta("21000.5"), UsageReport(0, 1_000_000, None, None)],
        ]
    )

    await run_turn(
        pool,
        session_id=session_id,
        model_entry=LUNA,
        provider=provider,
        queue=RecordingQueue(),
        tool_server=ServerWithTools(),  # pyright: ignore[reportArgumentType]
    )

    messages = await store.get_messages(db, session_id=session_id)
    rows = await db.fetch(
        "SELECT input_tokens, output_tokens, cost FROM usage WHERE message_id = $1 ORDER BY id",
        messages[-1].id,
    )

    assert len(rows) == 2
    assert [row["input_tokens"] for row in rows] == [1_000_000, 0]
    # Read through the aggregate the cost tab actually uses, not a fresh query: a turn
    # that billed twice must show as one sum there (specs/agent-usage, "Tura z
    # wywołaniem narzędzia").
    by_session = await store.usage_by_session(db, owner_principal="op-1", since=None, until=None)
    total = sum(aggregate.cost for aggregate in by_session)
    assert total == Decimal(1) + Decimal(6)


async def test_a_turn_with_no_tool_server_records_no_calls(pool, db) -> None:
    session_id = await _new_session(db)
    provider = FakeProvider([[TextDelta("no tools here"), UsageReport(10, 5, None, None)]])

    await run_turn(
        pool,
        session_id=session_id,
        model_entry=LUNA,
        provider=provider,
        queue=RecordingQueue(),
        tool_server=None,
    )

    messages = await store.get_messages(db, session_id=session_id)
    assert await store.get_tool_calls(db, message_id=messages[-1].id) == []


async def test_record_tool_calls_numbers_positions_within_each_round(pool, db) -> None:
    session_id = await _new_session(db)
    reply = await store.append_agent_message(
        db,
        session_id=session_id,
        content="answered",
        model_id=LUNA.id,
        prompt_version="v3",
        incomplete=False,
    )

    written = await store.record_tool_calls(
        db,
        session_id=session_id,
        message_id=reply.id,
        calls=[
            RecordedCall(round_index=0, name="a", arguments={}, outcome="ok", text="1", duration_ms=1),
            RecordedCall(round_index=0, name="b", arguments={}, outcome="ok", text="2", duration_ms=1),
            RecordedCall(round_index=1, name="c", arguments={}, outcome="ok", text="3", duration_ms=1),
        ],
    )

    assert [(call.round_index, call.position) for call in written] == [(0, 0), (0, 1), (1, 0)]


class ServerWithNoTools(FakeToolServer):
    """market-mcp unconfigured or unreachable — `list_tools` answers with nothing rather
    than raising, which is the whole of `agent-tool-access`'s "Brak serwera narzędzi nie
    odbiera agentowi mowy"."""

    async def list_tools(self):
        return []


async def test_a_turn_without_tools_runs_the_prompt_that_says_so(pool, db) -> None:
    # The prompt is picked from what the turn actually has, not from configuration: a
    # market-mcp that was configured and then went down must not leave the model being
    # told it has tools it cannot call (specs/agent-chat, "Agent bez narzędzi mówi, że
    # ich nie ma").
    session_id = await _new_session(db)
    provider = FakeProvider([[TextDelta("no archive today"), UsageReport(1, 1, None, None)]])

    await run_turn(
        pool,
        session_id=session_id,
        model_entry=LUNA,
        provider=provider,
        queue=RecordingQueue(),
        tool_server=ServerWithNoTools(),  # pyright: ignore[reportArgumentType]
    )

    assert provider.calls[0]["tools"] == []
    assert provider.calls[0]["system_prompt"] == SYSTEM_PROMPT_WITHOUT_TOOLS


async def test_a_turn_with_tools_runs_the_prompt_that_says_that(pool, db) -> None:
    session_id = await _new_session(db)
    provider = FakeProvider([[TextDelta("checking"), UsageReport(1, 1, None, None)]])

    await run_turn(
        pool,
        session_id=session_id,
        model_entry=LUNA,
        provider=provider,
        queue=RecordingQueue(),
        tool_server=ServerWithTools(),  # pyright: ignore[reportArgumentType]
    )

    assert [tool.name for tool in provider.calls[0]["tools"]] == ["get_last_price"]
    assert provider.calls[0]["system_prompt"] == SYSTEM_PROMPT_WITH_TOOLS
