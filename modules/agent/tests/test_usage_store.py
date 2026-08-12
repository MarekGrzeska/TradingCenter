from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from agent import store

pytestmark = pytest.mark.db


async def _reply_with_usage(
    conn,
    *,
    owner: str = "op-1",
    model_id: str = "gpt-5.6-luna",
    input_tokens: int | None,
    output_tokens: int | None,
    input_rate: Decimal = Decimal(1),
    output_rate: Decimal = Decimal(6),
):
    session = await store.create_session(conn, owner_principal=owner, model_id=model_id)
    await store.append_operator_message(conn, session_id=session.id, content="hi")
    reply = await store.append_agent_message(
        conn,
        session_id=session.id,
        content="hello",
        model_id=model_id,
        prompt_version="v1",
        incomplete=False,
    )
    usage = await store.record_usage(
        conn,
        session_id=session.id,
        message_id=reply.id,
        model_id=model_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_tokens=None,
        reasoning_tokens=None,
        input_rate_per_1m=input_rate,
        output_rate_per_1m=output_rate,
    )
    return session, usage


async def test_usage_by_model_sums_known_and_counts_unknown(db) -> None:
    await _reply_with_usage(db, model_id="gpt-5.6-luna", input_tokens=1000, output_tokens=500)
    await _reply_with_usage(db, model_id="gpt-5.6-luna", input_tokens=None, output_tokens=None)
    await _reply_with_usage(db, model_id="gpt-5.6-sol", input_tokens=200, output_tokens=100)

    by_model = {a.key: a for a in await store.usage_by_model(
        db, owner_principal="op-1", since=None, until=None
    )}

    assert by_model["gpt-5.6-luna"].input_tokens == 1000
    assert by_model["gpt-5.6-luna"].unknown_count == 1
    assert by_model["gpt-5.6-sol"].input_tokens == 200
    assert by_model["gpt-5.6-sol"].unknown_count == 0


async def test_usage_by_session_is_one_row_per_session(db) -> None:
    session_a, _ = await _reply_with_usage(db, input_tokens=100, output_tokens=50)
    session_b, _ = await _reply_with_usage(db, input_tokens=200, output_tokens=100)

    by_session = {a.key: a for a in await store.usage_by_session(
        db, owner_principal="op-1", since=None, until=None
    )}

    assert by_session[str(session_a.id)].input_tokens == 100
    assert by_session[str(session_b.id)].input_tokens == 200


async def test_usage_by_day_buckets_by_calendar_day(db) -> None:
    await _reply_with_usage(db, input_tokens=100, output_tokens=50)
    rows = await store.usage_by_day(db, owner_principal="op-1", since=None, until=None)
    assert len(rows) == 1
    assert rows[0].key == datetime.now(UTC).strftime("%Y-%m-%d")


async def test_total_cost_matches_the_sum_of_known_rows(db) -> None:
    await _reply_with_usage(
        db,
        input_tokens=1000,
        output_tokens=500,
        input_rate=Decimal(1),
        output_rate=Decimal(6),
    )
    total = await store.usage_total_cost(db, owner_principal="op-1", since=None, until=None)
    assert total == Decimal("0.001") + Decimal("0.003")


async def test_unknown_usage_does_not_count_as_zero_cost(db) -> None:
    # specs/agent-usage, "Zużycia, którego dostawca nie podał, MUST NOT być zgadywane"
    # — an unpriceable row must be visibly absent from the sum, not silently zero.
    await _reply_with_usage(db, input_tokens=None, output_tokens=None)
    total = await store.usage_total_cost(db, owner_principal="op-1", since=None, until=None)
    assert total == Decimal(0)
    by_model = await store.usage_by_model(db, owner_principal="op-1", since=None, until=None)
    assert by_model[0].unknown_count == 1


async def test_an_empty_range_is_an_empty_result_not_an_error(db) -> None:
    await _reply_with_usage(db, input_tokens=100, output_tokens=50)
    far_future = datetime.now(UTC) + timedelta(days=365)
    rows = await store.usage_by_model(
        db, owner_principal="op-1", since=far_future, until=None
    )
    total = await store.usage_total_cost(db, owner_principal="op-1", since=far_future, until=None)
    assert rows == []
    assert total == Decimal(0)


async def test_aggregation_is_scoped_to_the_callers_own_sessions(db) -> None:
    await _reply_with_usage(db, owner="op-1", input_tokens=100, output_tokens=50)
    await _reply_with_usage(db, owner="op-2", input_tokens=999, output_tokens=999)

    rows = await store.usage_by_model(db, owner_principal="op-1", since=None, until=None)
    assert len(rows) == 1
    assert rows[0].input_tokens == 100


async def test_a_later_rate_does_not_change_an_earlier_rows_cost(db) -> None:
    # specs/agent-usage, "Koszt jest przypisany do wiersza w chwili zapisu" — the
    # mechanism itself: recording a second row on a different rate must not touch the
    # first.
    _, first = await _reply_with_usage(
        db, input_tokens=1000, output_tokens=0, input_rate=Decimal(1), output_rate=Decimal(6)
    )
    await _reply_with_usage(
        db, input_tokens=1000, output_tokens=0, input_rate=Decimal(2), output_rate=Decimal(12)
    )
    total = await store.usage_total_cost(db, owner_principal="op-1", since=None, until=None)
    assert first.cost == Decimal("0.001")
    assert total == Decimal("0.001") + Decimal("0.002")
