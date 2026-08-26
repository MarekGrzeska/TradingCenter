"""The transcript on the wire, field by field. The terminal holds hand-written DTOs against this contract —
there is no generator to fail here — so a new field would reach it as an unannounced change.

The previous version asserted that nothing about tools reached the transcript, and said the change showing
them was the one to edit it. This is that edit."""

from __future__ import annotations

from datetime import UTC, datetime

from agent.contract import MessageOut, ToolCallOut
from agent.models import Message, RecordedCall, Role, ToolCall

TRANSCRIPT_FIELDS = {
    "id",
    "role",
    "content",
    "model_id",
    "prompt_version",
    "incomplete",
    "stopped",
    "created_at",
    "tool_calls",
}

TOOL_CALL_FIELDS = {
    "round_index",
    "position",
    "tool_name",
    "arguments",
    "outcome",
    "result_text",
    "duration_ms",
    "source",
}


def _message(role: Role = Role.AGENT) -> Message:
    return Message(
        id=7,
        session_id=1,
        role=role,
        content="US100 is at 29698.2",
        model_id="gpt-5.6-luna" if role is Role.AGENT else None,
        prompt_version="v3" if role is Role.AGENT else None,
        incomplete=False,
        stopped=False,
        created_at=datetime(2026, 8, 13, tzinfo=UTC),
    )


def _row(**overrides) -> ToolCall:
    defaults = {
        "id": 1,
        "session_id": 1,
        "message_id": 7,
        "round_index": 0,
        "position": 0,
        "tool_name": "get_last_price",
        "arguments": {"symbol": "US100", "resolution": "DAY"},
        "outcome": "ok",
        "result_text": '{"close": 29698.2}',
        "duration_ms": 63,
        "created_at": datetime(2026, 8, 13, tzinfo=UTC),
    }
    return ToolCall(**{**defaults, **overrides})


def test_a_message_on_the_wire_carries_exactly_these_fields() -> None:
    assert set(MessageOut.model_fields) == TRANSCRIPT_FIELDS


def test_a_tool_call_on_the_wire_carries_exactly_these_fields() -> None:
    assert set(ToolCallOut.model_fields) == TOOL_CALL_FIELDS


def test_a_message_with_no_calls_carries_an_empty_list_not_a_null() -> None:
    """specs/agent-tools, "Wypowiedź bez narzędzi" — absent and empty are two different
    facts, and a nullable field says only one of them."""
    published = MessageOut.from_message(_message()).model_dump()

    assert published["tool_calls"] == []


def test_an_operator_message_carries_an_empty_list_too() -> None:
    published = MessageOut.from_message(_message(Role.OPERATOR)).model_dump()

    assert published["tool_calls"] == []


def test_calls_reach_the_transcript_in_the_order_they_were_made() -> None:
    calls = [
        _row(id=1, round_index=0, position=0, tool_name="list_tracked_pairs"),
        _row(id=2, round_index=0, position=1, tool_name="describe_coverage"),
        _row(id=3, round_index=1, position=0, tool_name="get_candles"),
    ]

    published = MessageOut.from_message(_message(), calls).model_dump()

    assert [c["tool_name"] for c in published["tool_calls"]] == [
        "list_tracked_pairs",
        "describe_coverage",
        "get_candles",
    ]
    assert [(c["round_index"], c["position"]) for c in published["tool_calls"]] == [
        (0, 0),
        (0, 1),
        (1, 0),
    ]


def test_the_stream_and_the_transcript_publish_one_shape() -> None:
    """The whole reason `ToolCallOut` has two constructors. A panel that keeps what the
    stream gave it and a panel that reloads the transcript MUST hold the same thing."""
    row = _row(outcome="refused", result_text="market-data refused: no such pair")
    live = RecordedCall(
        round_index=row.round_index,
        name=row.tool_name,
        arguments=row.arguments,
        outcome=row.outcome,
        text=row.result_text,
        duration_ms=row.duration_ms,
    )

    from_stream = ToolCallOut.from_recorded(live, row.position).model_dump()
    from_transcript = ToolCallOut.from_tool_call(row).model_dump()

    assert from_stream == from_transcript
