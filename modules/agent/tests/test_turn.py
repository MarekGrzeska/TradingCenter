from __future__ import annotations

from decimal import Decimal

import pytest

from agent import store
from agent.config import ModelCatalogueEntry
from agent.provider import TextDelta, UsageReport
from agent.turn import Complete, Failed, Fragment, run_turn

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


class FakeProvider:
    """Yields a scripted list of chunks, optionally raising once they are exhausted —
    a stand-in for a provider that broke partway through (`agent/graph.py`'s node
    catches this and returns whatever text was already accumulated)."""

    def __init__(self, chunks: list, *, then_raise: bool = False) -> None:
        self._chunks = chunks
        self._then_raise = then_raise

    async def stream(
        self, *, model: str, system_prompt: str, history: list, tools=(), rounds=()
    ):
        for chunk in self._chunks:
            yield chunk
        if self._then_raise:
            raise RuntimeError("provider broke")


async def _new_session(conn) -> int:
    session = await store.create_session(conn, owner_principal="op-1", model_id=LUNA.id)
    await store.append_operator_message(conn, session_id=session.id, content="hello")
    return session.id


async def test_fragments_arrive_before_completion(pool, db) -> None:
    session_id = await _new_session(db)
    provider = FakeProvider([TextDelta("hi "), TextDelta("there"), UsageReport(10, 5, None, None)])
    queue = RecordingQueue()

    await run_turn(pool, session_id=session_id, model_entry=LUNA, provider=provider, queue=queue)

    assert queue.events[:2] == [Fragment("hi "), Fragment("there")]
    assert queue.events[-1] == Complete(incomplete=False)

    messages = await store.get_messages(db, session_id=session_id)
    assert messages[-1].content == "hi there"
    assert messages[-1].incomplete is False


async def test_an_abandoned_queue_still_gets_the_full_reply_written(pool, db) -> None:
    # specs/agent-chat, "Wołający rozłącza się w trakcie" — nothing here ever reads
    # `queue.events`; `run_turn` must not care whether anyone is listening.
    session_id = await _new_session(db)
    provider = FakeProvider(
        [TextDelta("a"), TextDelta("b"), TextDelta("c"), UsageReport(1, 1, None, None)]
    )
    queue = RecordingQueue()

    await run_turn(pool, session_id=session_id, model_entry=LUNA, provider=provider, queue=queue)

    messages = await store.get_messages(db, session_id=session_id)
    assert messages[-1].content == "abc"
    assert messages[-1].incomplete is False


async def test_a_broken_stream_saves_the_partial_reply_as_incomplete(pool, db) -> None:
    # specs/agent-chat, "Model przerywa w połowie"
    session_id = await _new_session(db)
    provider = FakeProvider([TextDelta("cut "), TextDelta("off")], then_raise=True)
    queue = RecordingQueue()

    await run_turn(pool, session_id=session_id, model_entry=LUNA, provider=provider, queue=queue)

    messages = await store.get_messages(db, session_id=session_id)
    assert messages[-1].content == "cut off"
    assert messages[-1].incomplete is True
    assert queue.events[-1] == Failed("the model call failed")


async def test_usage_never_reported_is_recorded_as_unknown_not_skipped(pool, db) -> None:
    # specs/agent-usage, "Każde wywołanie modelu zostawia ślad zużycia" — even a call
    # that broke before reporting anything leaves a row, not silence.
    session_id = await _new_session(db)
    provider = FakeProvider([TextDelta("x")], then_raise=True)
    queue = RecordingQueue()

    await run_turn(pool, session_id=session_id, model_entry=LUNA, provider=provider, queue=queue)

    reply = (await store.get_messages(db, session_id=session_id))[-1]
    rows = await db.fetch("SELECT * FROM usage WHERE message_id = $1", reply.id)
    assert len(rows) == 1
    assert rows[0]["input_tokens"] is None
    assert rows[0]["cost"] is None


async def test_a_reply_keeps_its_version_after_the_prompt_is_later_edited(pool, db) -> None:
    # specs/agent-prompt-management, "Odpowiedź niesie wersję, pod jaką faktycznie
    # padła" — editing the prompt between two turns of the same rozmowa must not
    # reach back and relabel the first one.
    session_id = await _new_session(db)
    provider = FakeProvider([TextDelta("first"), UsageReport(1, 1, None, None)])
    await run_turn(pool, session_id=session_id, model_entry=LUNA, provider=provider, queue=RecordingQueue())

    first_reply = (await store.get_messages(db, session_id=session_id))[-1]
    assert first_reply.prompt_version == "v7"

    await store.create_prompt_revision(db, with_tools_body="edited", without_tools_body="edited")

    await store.append_operator_message(db, session_id=session_id, content="again")
    provider = FakeProvider([TextDelta("second"), UsageReport(1, 1, None, None)])
    await run_turn(pool, session_id=session_id, model_entry=LUNA, provider=provider, queue=RecordingQueue())

    messages = await store.get_messages(db, session_id=session_id)
    second_reply = messages[-1]
    assert second_reply.prompt_version == "v8"

    first_reply_reread = next(m for m in messages if m.id == first_reply.id)
    assert first_reply_reread.prompt_version == "v7"


async def test_usage_reported_before_a_failure_is_still_recorded(pool, db) -> None:
    # specs/agent-usage, "Wywołanie zakończone błędem po tym, jak model zaczął
    # odpowiadać, MUST zapisać zużycie, które zdążyło powstać"
    session_id = await _new_session(db)
    provider = FakeProvider(
        [TextDelta("x"), UsageReport(5, 2, None, None)], then_raise=True
    )
    queue = RecordingQueue()

    await run_turn(pool, session_id=session_id, model_entry=LUNA, provider=provider, queue=queue)

    reply = (await store.get_messages(db, session_id=session_id))[-1]
    rows = await db.fetch("SELECT * FROM usage WHERE message_id = $1", reply.id)
    assert rows[0]["input_tokens"] == 5
    assert rows[0]["output_tokens"] == 2
