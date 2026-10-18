"""From a fire to a message: what is written, what is tried again, what is let go and what is never sent twice. The
door's own answers are `FakeGateway`'s; its mapping from HTTP is the last test."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from alerts import store
from alerts.delivery import Deliverer
from alerts.gateway import Gateway, Sent

from .builders import condition, event, rule

T0 = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)


async def fire_of(pool, candidate=None, *, text: str = "message", at: datetime = T0, edge: int = 0) -> tuple[int, int]:
    """A rule and a pending fire for it, as the clock or a publication would have left them."""
    async with pool.acquire() as conn:
        row = await store.insert_rule(conn, candidate or rule(condition(), cooldown_seconds=0), created_by="operator", now=at)
        fire = await store.record_fire(conn, row["id"], edge_at=at + timedelta(seconds=edge), text=text, value=1.1, now=at)
    assert fire is not None
    return row["id"], fire


async def more_fires(pool, rule_id: int, count: int, at: datetime = T0) -> None:
    async with pool.acquire() as conn:
        for index in range(1, count + 1):
            await store.record_fire(conn, rule_id, edge_at=at + timedelta(seconds=index), text=f"message {index}", value=1.1, now=at)


@pytest.fixture
def deliverer(pool, settings, door) -> Deliverer:
    return Deliverer(pool, settings, door)


async def state_of(db, fire_id: int) -> tuple[str, str | None]:
    row = await db.fetchrow("SELECT state, reason FROM fires WHERE id = $1", fire_id)
    return row["state"], row["reason"]


pytestmark = pytest.mark.db


async def test_a_fire_is_sent_to_the_rules_recipient_and_marked_delivered(deliverer, pool, door, db) -> None:
    _, fire = await fire_of(pool, text="EURUSD is over 1.10")

    await deliverer.run(T0)

    assert door.sent == [("phone", "EURUSD is over 1.10")]
    assert (await state_of(db, fire))[0] == "delivered"
    assert await db.fetchval("SELECT delivered_at FROM fires WHERE id = $1", fire) == T0


async def test_a_fire_claimed_is_left_alone_until_its_lease_runs_out(deliverer, pool, door) -> None:
    await fire_of(pool)

    await deliverer.run(T0)
    await deliverer.run(T0)

    assert len(door.sent) == 1


async def test_a_refusal_that_would_come_again_is_final_and_is_not_asked_twice(deliverer, pool, door, db) -> None:
    _, fire = await fire_of(pool)
    door.answers = [Sent(ok=False, reason="the recipient blocked the bot")]

    await deliverer.run(T0)
    await deliverer.run(T0 + timedelta(hours=1))

    assert await state_of(db, fire) == ("refused", "the recipient blocked the bot")
    assert len(door.sent) == 1


async def test_a_door_that_cannot_be_reached_is_asked_again_after_the_wait_it_named(deliverer, pool, door, db) -> None:
    _, fire = await fire_of(pool)
    door.answers = [Sent(ok=False, transient=True, retry_after_seconds=120, reason="slow down")]

    await deliverer.run(T0)
    assert (await state_of(db, fire))[0] == "pending"
    await deliverer.run(T0 + timedelta(seconds=100))
    assert len(door.sent) == 1
    await deliverer.run(T0 + timedelta(seconds=121))

    assert len(door.sent) == 2
    assert (await state_of(db, fire))[0] == "delivered"


async def test_what_the_door_missed_for_an_hour_arrives_when_it_returns(deliverer, pool, door, db) -> None:
    _, fire = await fire_of(pool)
    door.answers = [Sent(ok=False, transient=True, reason="down")] * 3

    for minutes in (0, 10, 20):
        await deliverer.run(T0 + timedelta(minutes=minutes))
    await deliverer.run(T0 + timedelta(minutes=60))

    assert (await state_of(db, fire))[0] == "delivered"


async def test_what_the_door_missed_for_longer_than_the_window_is_let_go_unsent(deliverer, pool, door, db, settings) -> None:
    _, fire = await fire_of(pool)
    door.answers = [Sent(ok=False, transient=True, reason="down")]
    await deliverer.run(T0)

    late = T0 + timedelta(hours=settings.retry_window_hours, minutes=5)
    await deliverer.run(late)

    assert (await state_of(db, fire))[0] == "abandoned"
    assert len(door.sent) == 1


async def test_a_rule_that_tells_too_often_is_cut_at_its_cap_and_the_operator_is_told_once(pool, settings, door, db) -> None:
    rule_id, _ = await fire_of(pool, rule(condition(), cooldown_seconds=0, max_per_hour=3))
    await more_fires(pool, rule_id, 5)
    deliverer = Deliverer(pool, settings, door)

    await deliverer.run(T0)
    await deliverer.run(T0 + timedelta(minutes=1))

    states = [row["state"] for row in await db.fetch("SELECT state FROM fires WHERE rule_id = $1 ORDER BY id", rule_id)]
    assert states.count("delivered") == 3 and states.count("throttled") == 3
    notices = [text for _, text in door.sent if "zdławiona" in text]
    assert len(notices) == 1


async def test_a_one_time_rule_is_switched_off_when_its_one_message_is_delivered(deliverer, pool, db) -> None:
    rule_id, _ = await fire_of(pool, rule(condition(), mode="once"))

    await deliverer.run(T0)

    row = await db.fetchrow("SELECT enabled, disabled_reason FROM rules WHERE id = $1", rule_id)
    assert (row["enabled"], row["disabled_reason"]) == (False, "fired")


async def test_a_one_time_rule_whose_message_never_arrives_may_fire_again(deliverer, pool, door, db) -> None:
    rule_id, _ = await fire_of(pool, rule(condition(), mode="once"))
    door.answers = [Sent(ok=False, reason="no such recipient")]

    await deliverer.run(T0)

    row = await db.fetchrow("SELECT enabled, last_fired_at FROM rules WHERE id = $1", rule_id)
    assert (row["enabled"], row["last_fired_at"]) == (True, None)


async def test_a_rule_switched_off_after_it_fired_does_not_send_what_it_had_queued(deliverer, pool, door, db) -> None:
    rule_id, fire = await fire_of(pool)
    async with pool.acquire() as conn:
        await store.set_enabled(conn, rule_id, False, now=T0)

    await deliverer.run(T0)

    assert door.sent == []
    assert (await state_of(db, fire))[0] == "abandoned"


async def test_no_door_in_the_process_is_a_state_of_the_fire_not_a_crash(pool, settings, db) -> None:
    _, fire = await fire_of(pool)

    await Deliverer(pool, settings, None).run(T0)

    state, reason = await state_of(db, fire)
    assert (state, reason) == ("undeliverable", "there is no door to Telegram in this process")


async def test_an_event_rule_is_delivered_the_same_way(deliverer, pool, door, db) -> None:
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO event_types (name, description, schema) VALUES ('youtube.film.read', 'd', '{}')")
    _, fire = await fire_of(pool, rule(event()), text="a film")

    await deliverer.run(T0)

    assert door.sent == [("phone", "a film")]
    assert (await state_of(db, fire))[0] == "delivered"


@pytest.mark.parametrize(
    ("status", "body", "expected"),
    [
        (200, {"destination": "phone", "message_id": 1, "chat_id": 2}, Sent(ok=True)),
        (429, {"detail": {"detail": "slow down", "retryable": True, "retry_after_seconds": 7}}, Sent(ok=False, transient=True, retry_after_seconds=7, reason="slow down")),
        (502, {"detail": {"detail": "Telegram is out of reach", "retryable": True}}, Sent(ok=False, transient=True, reason="Telegram is out of reach")),
        (503, {"detail": {"detail": "busy"}}, Sent(ok=False, transient=True, reason="busy")),
        (409, {"detail": {"detail": "blocked the bot"}}, Sent(ok=False, reason="blocked the bot")),
        (404, {"detail": {"detail": "no destination 'phone'"}}, Sent(ok=False, reason="no destination 'phone'")),
        (502, {"detail": {"detail": "chat not found", "retryable": False}}, Sent(ok=False, reason="chat not found")),
    ],
)
async def test_the_doors_answers_are_read_as_final_or_ask_again(status, body, expected) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(status, json=body))
    gateway = Gateway(httpx.AsyncClient(transport=transport, base_url="http://door"))

    assert await gateway.send("phone", "text") == expected


async def test_a_door_that_does_not_answer_is_asked_again() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    gateway = Gateway(httpx.AsyncClient(transport=httpx.MockTransport(refuse), base_url="http://door"))

    sent = await gateway.send("phone", "text")

    assert (sent.ok, sent.transient) == (False, True)
