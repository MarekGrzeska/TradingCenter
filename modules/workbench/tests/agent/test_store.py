from __future__ import annotations

from decimal import Decimal

import pytest

from agent import store
from agent.models import Role

pytestmark = pytest.mark.db


def test_derive_title_collapses_whitespace_and_truncates() -> None:
    assert store.derive_title("  hello   world  ") == "hello world"
    long = "x" * 100
    title = store.derive_title(long)
    assert len(title) == 60
    assert title.endswith("…")


async def test_a_session_with_no_messages_is_not_listed(db) -> None:
    # specs/agent-chat, "Pusta sesja nie zaśmieca historii"
    session = await store.create_session(db, owner_principal="op-1", model_id="gpt-5.6-luna")
    listed = await store.list_sessions(db, owner_principal="op-1")
    assert listed == []

    await store.append_operator_message(db, session_id=session.id, content="hello")
    listed = await store.list_sessions(db, owner_principal="op-1")
    assert [s.id for s in listed] == [session.id]
    assert listed[0].title == "hello"


async def test_message_order_is_stable_and_repeatable(db) -> None:
    # specs/agent-chat, "Transkrypt zachowuje kolejność i autorstwo"
    session = await store.create_session(db, owner_principal="op-1", model_id="gpt-5.6-luna")
    await store.append_operator_message(db, session_id=session.id, content="first")
    await store.append_agent_message(
        db,
        session_id=session.id,
        content="second",
        model_id="gpt-5.6-luna",
        prompt_version="v1",
        incomplete=False,
    )
    await store.append_operator_message(db, session_id=session.id, content="third")

    first_read = await store.get_messages(db, session_id=session.id)
    second_read = await store.get_messages(db, session_id=session.id)
    assert [m.content for m in first_read] == ["first", "second", "third"]
    assert [m.id for m in first_read] == [m.id for m in second_read]


async def test_operator_message_survives_a_failed_model_call(db) -> None:
    # specs/agent-chat, "Wypowiedź operatora MUST być zapisana zanim moduł zawoła model"
    session = await store.create_session(db, owner_principal="op-1", model_id="gpt-5.6-luna")
    await store.append_operator_message(db, session_id=session.id, content="hello")
    # No agent message is ever appended — this simulates the model call failing before
    # any reply exists — and the operator's turn must still be there.
    messages = await store.get_messages(db, session_id=session.id)
    assert len(messages) == 1
    assert messages[0].role == Role.OPERATOR


async def test_a_foreign_session_reads_as_missing(db) -> None:
    # specs/agent-browser-access, "Odmowa dostępu do cudzej sesji MUST być
    # nieodróżnialna od odpowiedzi o sesji nieistniejącej"
    session = await store.create_session(db, owner_principal="op-1", model_id="gpt-5.6-luna")
    assert await store.get_session(db, session_id=session.id, owner_principal="op-2") is None
    assert await store.get_session(db, session_id=999_999, owner_principal="op-1") is None
    assert (await store.get_session(db, session_id=session.id, owner_principal="op-1")) is not None


async def test_changing_model_does_not_rewrite_earlier_messages(db) -> None:
    # specs/agent-models, "Model jest wyborem sesji, a nie instalacji"
    session = await store.create_session(db, owner_principal="op-1", model_id="gpt-5.6-luna")
    await store.append_operator_message(db, session_id=session.id, content="hello")
    early_reply = await store.append_agent_message(
        db,
        session_id=session.id,
        content="answer on luna",
        model_id="gpt-5.6-luna",
        prompt_version="v1",
        incomplete=False,
    )
    await store.set_session_model(
        db, session_id=session.id, owner_principal="op-1", model_id="gpt-5.6-sol"
    )
    later_reply = await store.append_agent_message(
        db,
        session_id=session.id,
        content="answer on sol",
        model_id="gpt-5.6-sol",
        prompt_version="v1",
        incomplete=False,
    )
    assert early_reply.model_id == "gpt-5.6-luna"
    assert later_reply.model_id == "gpt-5.6-sol"


async def test_an_incomplete_reply_is_marked(db) -> None:
    # specs/agent-chat, "Model przerywa w połowie"
    session = await store.create_session(db, owner_principal="op-1", model_id="gpt-5.6-luna")
    await store.append_operator_message(db, session_id=session.id, content="hello")
    reply = await store.append_agent_message(
        db,
        session_id=session.id,
        content="cut off mid",
        model_id="gpt-5.6-luna",
        prompt_version="v1",
        incomplete=True,
    )
    assert reply.incomplete is True
    assert reply.stopped is False


async def test_a_stopped_reply_is_marked_apart_from_a_broken_one(db) -> None:
    """Read back from the transcript, not only from the return value, because that is where a later reader
    looks."""
    session = await store.create_session(db, owner_principal="op-1", model_id="gpt-5.6-luna")
    await store.append_operator_message(db, session_id=session.id, content="hello")
    await store.append_agent_message(
        db,
        session_id=session.id,
        content="the model broke here",
        model_id="gpt-5.6-luna",
        prompt_version="v1",
        incomplete=True,
    )
    stopped = await store.append_agent_message(
        db,
        session_id=session.id,
        content="the operator stopped here",
        model_id="gpt-5.6-luna",
        prompt_version="v1",
        incomplete=True,
        stopped=True,
    )
    assert stopped.stopped is True

    messages = await store.get_messages(db, session_id=session.id)
    broken, cut = messages[1], messages[2]
    # Both are incomplete; only one of them was somebody's decision.
    assert (broken.incomplete, broken.stopped) == (True, False)
    assert (cut.incomplete, cut.stopped) == (True, True)


async def test_usage_cost_is_computed_from_the_rates_given(db) -> None:
    session = await store.create_session(db, owner_principal="op-1", model_id="gpt-5.6-luna")
    await store.append_operator_message(db, session_id=session.id, content="hello")
    reply = await store.append_agent_message(
        db,
        session_id=session.id,
        content="hi",
        model_id="gpt-5.6-luna",
        prompt_version="v1",
        incomplete=False,
    )
    usage = await store.record_usage(
        db,
        session_id=session.id,
        message_id=reply.id,
        model_id="gpt-5.6-luna",
        input_tokens=1000,
        output_tokens=500,
        cached_tokens=None,
        reasoning_tokens=None,
        input_rate_per_1m=Decimal(1),
        output_rate_per_1m=Decimal(6),
    )
    assert usage.cost == Decimal("0.001") + Decimal("0.003")


async def test_usage_with_unknown_tokens_has_no_cost(db) -> None:
    # specs/agent-usage, "Zużycia, którego dostawca nie podał, MUST NOT być zgadywane"
    session = await store.create_session(db, owner_principal="op-1", model_id="gpt-5.6-luna")
    await store.append_operator_message(db, session_id=session.id, content="hello")
    reply = await store.append_agent_message(
        db,
        session_id=session.id,
        content="hi",
        model_id="gpt-5.6-luna",
        prompt_version="v1",
        incomplete=False,
    )
    usage = await store.record_usage(
        db,
        session_id=session.id,
        message_id=reply.id,
        model_id="gpt-5.6-luna",
        input_tokens=None,
        output_tokens=None,
        cached_tokens=None,
        reasoning_tokens=None,
        input_rate_per_1m=Decimal(1),
        output_rate_per_1m=Decimal(6),
    )
    assert usage.cost is None
    assert usage.input_tokens is None
