"""The clock against a real database: that what the decision says is what gets written, and that a rule is looked at by one
tick only. The decision itself is `test_conditions`'s."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from tc_runtime.liveness import LoopHeartbeat

from alerts import store
from alerts.clock import Clock
from alerts.gateway import Sent

from .builders import condition, rule

pytestmark = pytest.mark.db

T0 = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)


@pytest.fixture
def clock(pool, settings, tools) -> Clock:
    return Clock(pool, settings, tools, LoopHeartbeat("clock", expected_seconds=5))


async def saved(pool, candidate=None, now: datetime = T0) -> int:
    async with pool.acquire() as conn:
        row = await store.insert_rule(conn, candidate or rule(condition(poll_interval_seconds=60)), created_by="operator", now=now)
    return row["id"]


async def at(clock: Clock, seconds: int) -> int:
    return await clock.tick(T0 + timedelta(seconds=seconds))


async def fires(db, rule_id: int) -> list:
    return await db.fetch("SELECT text, value FROM fires WHERE rule_id = $1 ORDER BY id", rule_id)


async def checks(db, rule_id: int) -> list[str]:
    return [row["outcome"] for row in await db.fetch("SELECT outcome FROM rule_checks WHERE rule_id = $1 ORDER BY id", rule_id)]


async def test_a_price_that_crosses_fires_once_with_the_message_of_the_template(clock, tools, pool, db) -> None:
    rule_id = await saved(pool)
    await at(clock, 0)  # baseline: 1.05, under the level
    tools.price = 1.12

    await at(clock, 60)
    await at(clock, 120)
    await at(clock, 180)

    found = await fires(db, rule_id)
    assert [row["text"] for row in found] == ["a rule: 1.12"]


async def test_a_rule_written_when_the_price_is_already_over_waits_for_the_next_crossing(clock, tools, pool, db) -> None:
    rule_id = await saved(pool)
    tools.price = 1.12
    await at(clock, 0)
    await at(clock, 60)
    assert await fires(db, rule_id) == []

    tools.price = 1.05
    await at(clock, 120)
    tools.price = 1.13
    await at(clock, 180)

    assert len(await fires(db, rule_id)) == 1


async def test_a_crossing_inside_the_cooldown_is_recorded_and_not_sent(clock, tools, pool, db) -> None:
    rule_id = await saved(pool, rule(condition(poll_interval_seconds=30), cooldown_seconds=900))
    await at(clock, 0)
    tools.price = 1.12
    await at(clock, 30)
    tools.price = 1.05
    await at(clock, 60)
    tools.price = 1.12
    await at(clock, 90)

    assert len(await fires(db, rule_id)) == 1
    assert await checks(db, rule_id) == ["cooldown"]


async def test_a_one_time_rule_whose_first_alert_is_still_waiting_does_not_fire_again_on_the_next_crossing(
    pool, settings, tools, door, db
) -> None:
    door.answers = [Sent(ok=False, transient=True, reason="busy")] * 10
    clock = Clock(pool, settings, tools, LoopHeartbeat("clock", expected_seconds=5), door)
    rule_id = await saved(pool, rule(condition(poll_interval_seconds=60), mode="once", cooldown_seconds=0))
    await at(clock, 0)
    tools.price = 1.12
    await at(clock, 60)
    tools.price = 1.05
    await at(clock, 120)
    tools.price = 1.13

    await at(clock, 180)

    assert len(await fires(db, rule_id)) == 1


async def test_an_outage_is_one_line_and_never_a_crossing(clock, tools, pool, db) -> None:
    rule_id = await saved(pool)
    tools.price = 1.12
    await at(clock, 0)  # baseline: over
    tools.down = True
    await at(clock, 60)
    await at(clock, 120)
    tools.down = False
    await at(clock, 180)  # back, still over: not a crossing

    assert await fires(db, rule_id) == []
    assert await checks(db, rule_id) == ["unavailable"]
    assert (await db.fetchval("SELECT last_result FROM rules WHERE id = $1", rule_id)) is True


async def test_a_closed_market_is_unavailable_and_a_refusal_is_told_apart(clock, tools, pool, db) -> None:
    rule_id = await saved(pool)
    tools.price = None
    await at(clock, 0)
    tools.price = 1.05
    tools.refuses = True
    await at(clock, 60)

    assert await checks(db, rule_id) == ["unavailable", "refused"]


async def test_a_rule_is_looked_at_once_per_interval_and_a_switched_off_one_not_at_all(clock, tools, pool, db) -> None:
    first = await saved(pool)
    second = await saved(pool, rule(condition(poll_interval_seconds=60), name="off", enabled=False))

    assert await at(clock, 0) == 1
    assert await at(clock, 30) == 0
    assert await at(clock, 61) == 1
    assert await db.fetchval("SELECT last_checked_at FROM rules WHERE id = $1", second) is None
    assert await db.fetchval("SELECT count(*) FROM rules WHERE id = $1", first) == 1


async def test_no_tool_surface_makes_every_value_rule_unavailable_and_none_fire(pool, settings, db) -> None:
    rule_id = await saved(pool)
    blind = Clock(pool, settings, None, LoopHeartbeat("clock", expected_seconds=5))

    await blind.tick(T0)

    assert await checks(db, rule_id) == ["unavailable"]
    assert await fires(db, rule_id) == []


async def test_the_clock_beats_its_heartbeat_and_stops_cleanly(pool, settings, tools) -> None:
    beat = LoopHeartbeat("clock", expected_seconds=5)
    running = Clock(pool, settings.model_copy(update={"tick_seconds": 0.05}), tools, beat)

    await running.start()
    running.wake()
    for _ in range(100):
        if beat.has_run:
            break
        import asyncio

        await asyncio.sleep(0.02)
    await running.stop()

    assert beat.has_run


async def test_a_held_clock_looks_at_nothing_until_it_is_let_go(pool, settings, tools) -> None:
    import asyncio

    ticks: list[int] = []
    held = Clock(pool, settings, tools, LoopHeartbeat("clock", expected_seconds=5), held=True)

    async def counted(now=None) -> int:
        ticks.append(1)
        return 0

    held.tick = counted  # type: ignore[method-assign]
    await held.start()
    await asyncio.sleep(0.05)
    assert ticks == []

    held.release()
    await asyncio.sleep(0.05)
    await held.stop()

    assert ticks != []


async def test_a_thousand_looks_that_never_fire_cost_no_model_and_leave_no_usage(clock, tools, pool, db) -> None:
    rule_id = await saved(pool)

    for second in range(0, 60 * 50, 60):
        await at(clock, second)

    assert await fires(db, rule_id) == []
    assert await db.fetchval("SELECT count(*) FROM draft_usage") == 0
