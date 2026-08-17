"""The clock firing schedules — `scheduler/clock.py` against a real database and a
scripted model, exercising `Clock.tick()` the way the module's own background task
would call it, every `SCHEDULER_POLL_INTERVAL_SECONDS`.

`_fire_schedule` (module-private) is used directly in the two tests that need to await
its failure-streak bookkeeping deterministically — `Clock.tick()` starts that bookkeeping
as a detached task on purpose, the same as production, and a test asserting on it needs
the handle `_fire_schedule` hands back (`test_run_loop.py` reaches into `runner.loop`'s
own internals for the same reason: some properties are only checkable from inside).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import asyncpg
import pytest
from croniter import croniter

from teams import store
from teams.contract import AgentDefinition, CostLimits, TeamDefinition, TradingLimits
from teams.models_catalogue import ModelCatalogue
from teams.runner import RunRegistry
from teams.scheduler.clock import Clock, _fire_schedule, _next_fire_and_skipped
from teams.tools import ToolServerRegistry

from .mcp_stand_in import settings_for
from .scripted_provider import ScriptedProvider, breaks, says

pytestmark = pytest.mark.db

OWNER = "operator-1"
MODEL_ID = "gpt-5.6-luna"

CRON = "*/5 * * * *"


def _past(cron: str = CRON) -> datetime:
    """A moment that is already due and has missed nothing — the schedule's own most
    recent slot.

    **Anchored to the cron grid, not to "a minute ago", and the difference is 20% of all
    wall-clock times.** `now - 1 minute` puts a `*/5` boundary between the due moment and
    now whenever the suite runs in the first minute after :00, :05, :10 … — so
    `_next_fire_and_skipped` correctly reports one folded slot and
    `test_a_due_schedule_starts_a_run_and_records_the_fire` correctly fails. It failed in
    CI at 05:15 for exactly this reason, having passed every local run that happened not
    to start on a boundary.

    Reading back from the grid removes the window rather than narrowing it: no slot lies
    between the last one and now, by construction.

    The second added before asking is what closes the last hole. `get_prev` is strict, so
    asked at exactly :05:00 it answers :00:00 — leaving the :05:00 slot between the due
    moment and now, and one folded slot again. Asking from a second later makes it "the
    last slot at or before now", which is the moment actually wanted.
    """
    now = datetime.now(UTC)
    return croniter(cron, now + timedelta(seconds=1)).get_prev(datetime)


FUTURE = datetime.now(UTC) + timedelta(hours=1)


def _definition(
    *,
    model_id: str = MODEL_ID,
    daily_limit: str | None = None,
    orders_per_day: int | None = None,
) -> TeamDefinition:
    return TeamDefinition(
        agents=[AgentDefinition(key="scout", role="scout", prompt="read the market", model_id=model_id)],
        limits=CostLimits(daily_limit=daily_limit),
        trading=TradingLimits(orders_per_day=orders_per_day),
    )


async def _team_and_revision(pool: asyncpg.Pool, definition: TeamDefinition) -> tuple[int, int]:
    async with pool.acquire() as conn:
        team, revision = await store.create_team(
            conn, owner_principal=OWNER, name="morning desk", description="", definition=definition
        )
    return team["id"], revision["id"]


async def _schedule(
    pool: asyncpg.Pool, *, team_id: int, revision_id: int, next_fire_at: datetime, cron: str = "*/5 * * * *"
) -> asyncpg.Record:
    async with pool.acquire() as conn:
        return await store.create_schedule(
            conn,
            team_id=team_id,
            owner_principal=OWNER,
            revision_mode="pinned",
            pinned_revision_id=revision_id,
            cron_expression=cron,
            next_fire_at=next_fire_at,
            unattended_ack=False,
        )


def _clock(pool: asyncpg.Pool, *, provider, settings=None) -> Clock:
    settings = settings or settings_for(None)
    return Clock(
        pool,
        catalogue=ModelCatalogue.from_settings(settings),
        provider=provider,
        tool_registry=ToolServerRegistry.from_settings(settings),
        settings=settings,
        registry=RunRegistry(),
    )


async def _fires(pool: asyncpg.Pool, *, schedule_id: int) -> list[asyncpg.Record]:
    async with pool.acquire() as conn:
        return await store.list_fires_for_schedule(conn, schedule_id=schedule_id, owner_principal=OWNER)


async def test_a_due_schedule_starts_a_run_and_records_the_fire(pool: asyncpg.Pool) -> None:
    team_id, revision_id = await _team_and_revision(pool, _definition())
    schedule = await _schedule(pool, team_id=team_id, revision_id=revision_id, next_fire_at=_past())

    clock = _clock(pool, provider=ScriptedProvider(default=says("the trend is up")))
    # `gather`-ed rather than left detached: `tick()` hands back the failure-streak
    # tasks precisely so a test can know every write this wake will ever make has
    # happened before the `pool` fixture tears down underneath a still-running one
    # (`Clock.tick()`'s own docstring).
    await asyncio.gather(*await clock.tick())

    fires = await _fires(pool, schedule_id=schedule["id"])
    assert len(fires) == 1
    assert fires[0]["outcome"] == "started"
    assert fires[0]["run_id"] is not None
    assert fires[0]["skipped_count"] == 0

    async with pool.acquire() as conn:
        run = await store.get_run(conn, run_id=fires[0]["run_id"], owner_principal=OWNER)
    assert run is not None
    assert run["team_revision_id"] == revision_id


async def test_a_schedule_not_yet_due_is_left_alone(pool: asyncpg.Pool) -> None:
    team_id, revision_id = await _team_and_revision(pool, _definition())
    schedule = await _schedule(pool, team_id=team_id, revision_id=revision_id, next_fire_at=FUTURE)

    clock = _clock(pool, provider=ScriptedProvider(default=says("done")))
    await clock.tick()

    assert await _fires(pool, schedule_id=schedule["id"]) == []


def test_next_fire_and_skipped_folds_every_due_slot_into_one() -> None:
    # Pure function, fixed instants — no wall-clock race, unlike the integration test
    # below. specs/teams-schedules, "Moduł nie pracował przez sześć godzin": due at 09:00,
    # now 15:30 — six hourly slots (10:00 through 15:00) are due, one fire, six folded in.
    due_at = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
    now = datetime(2026, 1, 1, 15, 30, tzinfo=UTC)

    next_fire_at, skipped = _next_fire_and_skipped("0 * * * *", due_at, now)

    assert skipped == 6
    assert next_fire_at == datetime(2026, 1, 1, 16, 0, tzinfo=UTC)


def test_next_fire_and_skipped_is_zero_for_a_schedule_right_on_time() -> None:
    due_at = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
    now = datetime(2026, 1, 1, 9, 1, tzinfo=UTC)

    next_fire_at, skipped = _next_fire_and_skipped("0 * * * *", due_at, now)

    assert skipped == 0
    assert next_fire_at == datetime(2026, 1, 1, 10, 0, tzinfo=UTC)


async def test_a_schedule_far_overdue_still_produces_exactly_one_run(pool: asyncpg.Pool) -> None:
    # The wall-clock counterpart of the two pure tests above: proves the engine actually
    # calls `_next_fire_and_skipped` and persists its result, without pinning an exact
    # count that a few milliseconds of test overhead near a cron boundary could flip.
    team_id, revision_id = await _team_and_revision(pool, _definition())
    before = datetime.now(UTC)
    schedule = await _schedule(
        pool,
        team_id=team_id,
        revision_id=revision_id,
        next_fire_at=before - timedelta(hours=3),
        cron="*/5 * * * *",
    )

    clock = _clock(pool, provider=ScriptedProvider(default=says("done")))
    await asyncio.gather(*await clock.tick())

    fires = await _fires(pool, schedule_id=schedule["id"])
    assert len(fires) == 1
    assert fires[0]["outcome"] == "started"
    assert fires[0]["skipped_count"] >= 34  # 3h / 5min, minus a slot or two of slack

    async with pool.acquire() as conn:
        after = await store.get_schedule(conn, schedule_id=schedule["id"], owner_principal=OWNER)
    assert after is not None
    assert after["next_fire_at"] > before


async def test_a_schedule_with_its_previous_run_still_working_is_skipped(pool: asyncpg.Pool) -> None:
    team_id, revision_id = await _team_and_revision(pool, _definition())
    schedule = await _schedule(pool, team_id=team_id, revision_id=revision_id, next_fire_at=_past())

    # A run that never gets a chance to finish inside this test — `pending`, forever.
    async with pool.acquire() as conn:
        stuck_run, _ = await store.create_run(
            conn, team_revision_id=revision_id, owner_principal=OWNER, agent_keys=["scout"]
        )
        await store.record_fire(conn, schedule_id=schedule["id"], outcome="started", run_id=stuck_run["id"])

    clock = _clock(pool, provider=ScriptedProvider(default=says("done")))
    await clock.tick()

    fires = await _fires(pool, schedule_id=schedule["id"])
    assert len(fires) == 2
    newest = fires[0]
    assert newest["outcome"] == "skipped"
    assert "still working" in newest["reason"]
    assert newest["run_id"] is None


async def test_a_revision_naming_a_model_outside_the_catalogue_is_skipped(pool: asyncpg.Pool) -> None:
    team_id, revision_id = await _team_and_revision(pool, _definition(model_id="gpt-9-imaginary"))
    schedule = await _schedule(pool, team_id=team_id, revision_id=revision_id, next_fire_at=_past())

    clock = _clock(pool, provider=ScriptedProvider(default=says("done")))
    await clock.tick()

    fires = await _fires(pool, schedule_id=schedule["id"])
    assert len(fires) == 1
    assert fires[0]["outcome"] == "skipped"
    assert "gpt-9-imaginary" in fires[0]["reason"]
    assert fires[0]["run_id"] is None


async def test_the_daily_cost_limit_stops_a_schedule_before_it_spends(pool: asyncpg.Pool) -> None:
    team_id, revision_id = await _team_and_revision(pool, _definition(daily_limit="1"))

    # A prior, unrelated run of this same team already spent past the daily ceiling.
    async with pool.acquire() as conn:
        earlier_run, steps = await store.create_run(
            conn, team_revision_id=revision_id, owner_principal=OWNER, agent_keys=["scout"]
        )
        await store.record_usage(
            conn,
            run_id=earlier_run["id"],
            run_step_id=steps[0]["id"],
            model_id=MODEL_ID,
            input_tokens=1_000_000,
            output_tokens=0,
            cached_tokens=None,
            reasoning_tokens=None,
            input_rate_per_1m=Decimal(5),
            output_rate_per_1m=Decimal(5),
        )

    schedule = await _schedule(pool, team_id=team_id, revision_id=revision_id, next_fire_at=_past())

    clock = _clock(pool, provider=ScriptedProvider(default=says("done")))
    await clock.tick()

    fires = await _fires(pool, schedule_id=schedule["id"])
    assert len(fires) == 1
    assert fires[0]["outcome"] == "skipped"
    assert "daily cost limit" in fires[0]["reason"]


async def _fire_directly(pool: asyncpg.Pool, schedule_id: int, *, provider, settings) -> None:
    """Calls `_fire_schedule` the way `Clock.tick()` does, and awaits the failure-streak
    task it hands back — `tick()` itself lets that task run detached, which is correct
    in production and untestable without this."""
    async with pool.acquire() as conn:
        await conn.execute("UPDATE schedules SET next_fire_at = $1 WHERE id = $2", _past(), schedule_id)
        row = await store.get_schedule(conn, schedule_id=schedule_id, owner_principal=OWNER)
    assert row is not None
    task = await _fire_schedule(
        pool,
        dict(row),
        catalogue=ModelCatalogue.from_settings(settings),
        provider=provider,
        tool_registry=ToolServerRegistry.from_settings(settings),
        settings=settings,
        registry=RunRegistry(),
    )
    assert task is not None
    await task


async def test_three_consecutive_failed_runs_disable_the_schedule(pool: asyncpg.Pool) -> None:
    team_id, revision_id = await _team_and_revision(pool, _definition())
    schedule = await _schedule(pool, team_id=team_id, revision_id=revision_id, next_fire_at=_past())
    settings = settings_for(None, scheduler_failure_threshold=3)

    for _ in range(3):
        await _fire_directly(
            pool, schedule["id"], provider=ScriptedProvider(default=breaks("provider is down")), settings=settings
        )

    async with pool.acquire() as conn:
        disabled = await store.get_schedule(conn, schedule_id=schedule["id"], owner_principal=OWNER)
    assert disabled is not None
    assert disabled["enabled"] is False
    assert "3" in disabled["disabled_reason"]


async def test_a_completed_run_resets_the_failure_streak(pool: asyncpg.Pool) -> None:
    team_id, revision_id = await _team_and_revision(pool, _definition())
    schedule = await _schedule(pool, team_id=team_id, revision_id=revision_id, next_fire_at=_past())
    settings = settings_for(None)

    await _fire_directly(
        pool, schedule["id"], provider=ScriptedProvider(default=breaks("provider is down")), settings=settings
    )
    async with pool.acquire() as conn:
        after_failure = await store.get_schedule(conn, schedule_id=schedule["id"], owner_principal=OWNER)
    assert after_failure is not None
    assert after_failure["consecutive_failures"] == 1

    await _fire_directly(pool, schedule["id"], provider=ScriptedProvider(default=says("done")), settings=settings)

    async with pool.acquire() as conn:
        after_success = await store.get_schedule(conn, schedule_id=schedule["id"], owner_principal=OWNER)
    assert after_success is not None
    assert after_success["consecutive_failures"] == 0
    assert after_success["enabled"] is True


async def test_a_disabled_clock_never_starts_a_background_task(pool: asyncpg.Pool) -> None:
    settings = settings_for(None, scheduler_enabled=False)
    clock = _clock(pool, provider=ScriptedProvider(default=says("done")), settings=settings)

    clock.start()

    assert clock._task is None


async def test_the_daily_order_limit_stops_a_schedule_and_leaves_a_row_rather_than_a_traceback(
    pool: asyncpg.Pool,
) -> None:
    """Phase 2 added a second daily ceiling to `start_run_on_revision` and the clock kept
    catching only the first, so this fire used to raise out of `tick()`: no row in the
    history, and every schedule and trigger after it in the same wake silently skipped.
    """
    team_id, revision_id = await _team_and_revision(pool, _definition(orders_per_day=1))

    async with pool.acquire() as conn:
        earlier_run, steps = await store.create_run(
            conn, team_revision_id=revision_id, owner_principal=OWNER, agent_keys=["scout"]
        )
        await store.record_trade(
            conn,
            run_id=earlier_run["id"],
            run_step_id=steps[0]["id"],
            agent_key="scout",
            tool_name="place_order",
            symbol="US100",
            direction="BUY",
            size=Decimal(1),
            level=None,
        )

    schedule = await _schedule(pool, team_id=team_id, revision_id=revision_id, next_fire_at=_past())

    clock = _clock(pool, provider=ScriptedProvider(default=says("done")))
    await asyncio.gather(*await clock.tick())

    fires = await _fires(pool, schedule_id=schedule["id"])
    assert len(fires) == 1
    assert fires[0]["outcome"] == "skipped"
    assert "order" in fires[0]["reason"]
    assert fires[0]["run_id"] is None


async def test_one_schedule_failing_does_not_silence_the_others_in_the_same_wake(
    pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The wake works every operator's schedules, so an exception escaping one of them
    must not take the rest of the list with it — `Clock._attempt`."""
    team_id, revision_id = await _team_and_revision(pool, _definition())
    first = await _schedule(pool, team_id=team_id, revision_id=revision_id, next_fire_at=_past())
    second = await _schedule(pool, team_id=team_id, revision_id=revision_id, next_fire_at=_past())

    from teams.scheduler import clock as clock_module

    real = clock_module._fire_schedule
    exploded: list[int] = []

    async def _explode_on_the_first(pool_, schedule, **kwargs):
        if schedule["id"] == first["id"]:
            exploded.append(schedule["id"])
            raise RuntimeError("the database went away mid-fire")
        return await real(pool_, schedule, **kwargs)

    monkeypatch.setattr(clock_module, "_fire_schedule", _explode_on_the_first)

    clock = _clock(pool, provider=ScriptedProvider(default=says("done")))
    await asyncio.gather(*await clock.tick())

    assert exploded == [first["id"]]
    assert await _fires(pool, schedule_id=first["id"]) == []
    survivors = await _fires(pool, schedule_id=second["id"])
    assert len(survivors) == 1
    assert survivors[0]["outcome"] == "started"
