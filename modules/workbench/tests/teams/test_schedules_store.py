"""Schedules, triggers and the fires either one produces — `store/` against a real
PostgreSQL, same reasoning as `test_store.py`: what is under test is the owner filter,
exactly-once claiming, and the three-valued state a trigger's own condition carries.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import asyncpg
import pytest

from teams import store
from teams.contract import AgentDefinition, TeamDefinition

pytestmark = pytest.mark.db

OWNER = "operator-1"
STRANGER = "operator-2"

PAST = datetime.now(UTC) - timedelta(minutes=1)
FUTURE = datetime.now(UTC) + timedelta(hours=1)


def _definition() -> TeamDefinition:
    return TeamDefinition(
        agents=[AgentDefinition(key="scout", role="scout", prompt="read the chart", model_id="luna")],
    )


async def _team_and_revision(db: asyncpg.Connection, *, owner: str = OWNER):
    team, revision = await store.create_team(
        db, owner_principal=owner, name="morning desk", description="", definition=_definition()
    )
    return team, revision


async def _schedule(
    db: asyncpg.Connection,
    *,
    owner: str = OWNER,
    team_id: int | None = None,
    revision_id: int | None = None,
    next_fire_at: datetime = FUTURE,
):
    if team_id is None or revision_id is None:
        team, revision = await _team_and_revision(db, owner=owner)
        team_id, revision_id = team["id"], revision["id"]
    return await store.create_schedule(
        db,
        team_id=team_id,
        owner_principal=owner,
        revision_mode="pinned",
        pinned_revision_id=revision_id,
        cron_expression="*/5 * * * *",
        next_fire_at=next_fire_at,
    )


async def _trigger(
    db: asyncpg.Connection,
    *,
    owner: str = OWNER,
    team_id: int | None = None,
    revision_id: int | None = None,
    next_check_at: datetime = FUTURE,
):
    if team_id is None or revision_id is None:
        team, revision = await _team_and_revision(db, owner=owner)
        team_id, revision_id = team["id"], revision["id"]
    return await store.create_trigger(
        db,
        team_id=team_id,
        owner_principal=owner,
        revision_mode="pinned",
        pinned_revision_id=revision_id,
        tool_name="get_candles",
        arguments={"epic": "EURUSD", "resolution": "MINUTE_15"},
        field_path="close",
        comparison="gt",
        threshold=Decimal("1.1"),
        cooldown_seconds=900,
        poll_interval_seconds=300,
        next_check_at=next_check_at,
    )


# --- schedules --------------------------------------------------------------------


async def test_a_schedule_belongs_to_its_owner(db: asyncpg.Connection) -> None:
    schedule = await _schedule(db)

    assert await store.get_schedule(db, schedule_id=schedule["id"], owner_principal=OWNER) is not None
    # specs/teams-schedules, "Harmonogram cudzego operatora": indistinguishable from one
    # that does not exist.
    assert await store.get_schedule(db, schedule_id=schedule["id"], owner_principal=STRANGER) is None


async def test_a_stranger_cannot_list_or_update_or_toggle_somebody_elses_schedule(
    db: asyncpg.Connection,
) -> None:
    schedule = await _schedule(db)

    assert await store.list_schedules_for_team(
        db, team_id=schedule["team_id"], owner_principal=STRANGER
    ) == []
    assert (
        await store.update_schedule(
            db,
            schedule_id=schedule["id"],
            owner_principal=STRANGER,
            revision_mode="latest",
            pinned_revision_id=None,
            cron_expression="0 * * * *",
            next_fire_at=FUTURE,
        )
        is None
    )
    assert (
        await store.set_schedule_enabled(
            db, schedule_id=schedule["id"], owner_principal=STRANGER, enabled=False
        )
        is None
    )


async def test_updating_a_schedule_switches_it_to_tracking_latest(db: asyncpg.Connection) -> None:
    schedule = await _schedule(db)

    updated = await store.update_schedule(
        db,
        schedule_id=schedule["id"],
        owner_principal=OWNER,
        revision_mode="latest",
        pinned_revision_id=None,
        cron_expression="0 9 * * MON-FRI",
        next_fire_at=FUTURE,
    )

    assert updated is not None
    assert updated["revision_mode"] == "latest"
    assert updated["pinned_revision_id"] is None
    assert updated["cron_expression"] == "0 9 * * MON-FRI"


async def test_re_enabling_a_schedule_clears_the_reason_and_the_failure_count(
    db: asyncpg.Connection,
) -> None:
    schedule = await _schedule(db)
    await store.disable_schedule_for_failures(
        db, schedule_id=schedule["id"], reason="3 kolejne przebiegi nieudane"
    )
    await store.increment_schedule_failures(db, schedule_id=schedule["id"])

    reenabled = await store.set_schedule_enabled(
        db, schedule_id=schedule["id"], owner_principal=OWNER, enabled=True
    )

    assert reenabled is not None
    assert reenabled["enabled"] is True
    assert reenabled["disabled_reason"] is None
    assert reenabled["consecutive_failures"] == 0


async def test_disabling_by_hand_leaves_no_reason_the_operator_did_not_write(
    db: asyncpg.Connection,
) -> None:
    # specs/terminal-teams-schedules and the store docstring: an operator's own choice
    # to pause a schedule needs no explanation manufactured for them.
    schedule = await _schedule(db)

    disabled = await store.set_schedule_enabled(
        db, schedule_id=schedule["id"], owner_principal=OWNER, enabled=False
    )

    assert disabled is not None
    assert disabled["enabled"] is False
    assert disabled["disabled_reason"] is None


async def test_the_module_disabling_a_schedule_names_a_reason(db: asyncpg.Connection) -> None:
    schedule = await _schedule(db)

    disabled = await store.disable_schedule_for_failures(
        db, schedule_id=schedule["id"], reason="3 kolejne przebiegi nieudane"
    )

    assert disabled is not None
    assert disabled["enabled"] is False
    assert disabled["disabled_reason"] == "3 kolejne przebiegi nieudane"


async def test_failures_increment_and_reset(db: asyncpg.Connection) -> None:
    schedule = await _schedule(db)

    await store.increment_schedule_failures(db, schedule_id=schedule["id"])
    twice = await store.increment_schedule_failures(db, schedule_id=schedule["id"])
    assert twice is not None
    assert twice["consecutive_failures"] == 2

    reset = await store.reset_schedule_failures(db, schedule_id=schedule["id"])
    assert reset is not None
    assert reset["consecutive_failures"] == 0


async def test_a_schedule_not_yet_due_is_not_claimed(db: asyncpg.Connection) -> None:
    schedule = await _schedule(db, next_fire_at=FUTURE)

    claimed = await store.claim_due_schedule(db, schedule_id=schedule["id"], next_fire_at=FUTURE)

    assert claimed is None


async def test_a_due_schedule_is_claimed_and_moved_forward(db: asyncpg.Connection) -> None:
    schedule = await _schedule(db, next_fire_at=PAST)
    next_slot = FUTURE

    claimed = await store.claim_due_schedule(db, schedule_id=schedule["id"], next_fire_at=next_slot)

    assert claimed is not None
    assert claimed["next_fire_at"] == next_slot

    # specs/teams-schedules, "Wyzwolenie jest przejmowane dokładnie raz": claiming again
    # right away finds the row no longer due.
    again = await store.claim_due_schedule(db, schedule_id=schedule["id"], next_fire_at=next_slot)
    assert again is None


async def test_two_processes_racing_the_same_due_schedule_give_exactly_one_winner(
    db: asyncpg.Connection, pool: asyncpg.Pool
) -> None:
    # specs/teams-schedules, "Dwa procesy przy jednym wyzwoleniu" — proven with two real
    # connections racing the same UPDATE, not two sequential calls on one.
    schedule = await _schedule(db, next_fire_at=PAST)

    async def _attempt() -> asyncpg.Record | None:
        async with pool.acquire() as conn:
            return await store.claim_due_schedule(conn, schedule_id=schedule["id"], next_fire_at=FUTURE)

    results = await asyncio.gather(_attempt(), _attempt())

    winners = [row for row in results if row is not None]
    assert len(winners) == 1


async def test_a_disabled_schedule_is_never_claimed_even_when_due(db: asyncpg.Connection) -> None:
    schedule = await _schedule(db, next_fire_at=PAST)
    await store.set_schedule_enabled(db, schedule_id=schedule["id"], owner_principal=OWNER, enabled=False)

    claimed = await store.claim_due_schedule(db, schedule_id=schedule["id"], next_fire_at=FUTURE)

    assert claimed is None


# --- triggers -----------------------------------------------------------------------


async def test_a_trigger_belongs_to_its_owner(db: asyncpg.Connection) -> None:
    trigger = await _trigger(db)

    assert await store.get_trigger(db, trigger_id=trigger["id"], owner_principal=OWNER) is not None
    assert await store.get_trigger(db, trigger_id=trigger["id"], owner_principal=STRANGER) is None


async def test_a_trigger_round_trips_its_condition(db: asyncpg.Connection) -> None:
    trigger = await _trigger(db)

    assert trigger["tool_name"] == "get_candles"
    assert trigger["field_path"] == "close"
    assert trigger["comparison"] == "gt"
    assert trigger["threshold"] == Decimal("1.10000000")
    # asyncpg hands JSONB back as text unless a codec is registered, same as
    # `team_revisions.definition` — contract.py is where this gets parsed back. Postgres
    # canonicalizes jsonb key order (shorter keys first) rather than keeping insertion
    # order, which happens to read the same here — `json.loads` below is what a real
    # caller relies on, not this literal string.
    assert json.loads(trigger["arguments"]) == {"epic": "EURUSD", "resolution": "MINUTE_15"}


async def test_updating_a_trigger_changes_its_condition(db: asyncpg.Connection) -> None:
    trigger = await _trigger(db)

    updated = await store.update_trigger(
        db,
        trigger_id=trigger["id"],
        owner_principal=OWNER,
        revision_mode="latest",
        pinned_revision_id=None,
        tool_name="get_candles",
        arguments={"epic": "GBPUSD", "resolution": "MINUTE_15"},
        field_path="close",
        comparison="lt",
        threshold=Decimal("0.85"),
        cooldown_seconds=1800,
        poll_interval_seconds=60,
    )

    assert updated is not None
    assert updated["comparison"] == "lt"
    assert updated["cooldown_seconds"] == 1800


async def test_a_trigger_not_yet_due_for_a_check_is_not_claimed(db: asyncpg.Connection) -> None:
    trigger = await _trigger(db, next_check_at=FUTURE)

    claimed = await store.claim_trigger_for_check(db, trigger_id=trigger["id"], next_check_at=FUTURE)

    assert claimed is None


async def test_two_processes_racing_the_same_trigger_check_give_exactly_one_winner(
    db: asyncpg.Connection, pool: asyncpg.Pool
) -> None:
    trigger = await _trigger(db, next_check_at=PAST)

    async def _attempt() -> asyncpg.Record | None:
        async with pool.acquire() as conn:
            return await store.claim_trigger_for_check(conn, trigger_id=trigger["id"], next_check_at=FUTURE)

    results = await asyncio.gather(_attempt(), _attempt())

    winners = [row for row in results if row is not None]
    assert len(winners) == 1


async def test_a_condition_the_tool_server_could_not_answer_is_recorded_as_unknown(
    db: asyncpg.Connection,
) -> None:
    # specs/teams-triggers, "Niedostępność serwera narzędzi to nie jest niespełniony
    # warunek" — NULL, not False.
    trigger = await _trigger(db)

    checked = await store.record_trigger_check(db, trigger_id=trigger["id"], result=None, fired=False)

    assert checked["last_result"] is None
    assert checked["last_fired_at"] is None


async def test_a_fire_stamps_last_fired_at_and_a_quiet_check_does_not(
    db: asyncpg.Connection,
) -> None:
    trigger = await _trigger(db)

    quiet = await store.record_trigger_check(db, trigger_id=trigger["id"], result=False, fired=False)
    assert quiet["last_result"] is False
    assert quiet["last_fired_at"] is None

    fired = await store.record_trigger_check(db, trigger_id=trigger["id"], result=True, fired=True)
    assert fired["last_result"] is True
    assert fired["last_fired_at"] is not None


# --- fires ----------------------------------------------------------------------------


async def test_a_fire_that_started_nothing_is_kept_with_its_reason(db: asyncpg.Connection) -> None:
    schedule = await _schedule(db)

    fire = await store.record_fire(
        db,
        schedule_id=schedule["id"],
        outcome="skipped",
        reason="the previous run is still working",
    )

    assert fire["outcome"] == "skipped"
    assert fire["run_id"] is None
    assert fire["reason"] == "the previous run is still working"


async def test_fire_history_is_owner_scoped_through_its_schedule(db: asyncpg.Connection) -> None:
    schedule = await _schedule(db)
    await store.record_fire(db, schedule_id=schedule["id"], outcome="skipped", reason="daily limit")

    assert len(await store.list_fires_for_schedule(db, schedule_id=schedule["id"], owner_principal=OWNER)) == 1
    assert (
        await store.list_fires_for_schedule(db, schedule_id=schedule["id"], owner_principal=STRANGER) == []
    )


async def test_fire_history_is_owner_scoped_through_its_trigger(db: asyncpg.Connection) -> None:
    trigger = await _trigger(db)
    await store.record_fire(db, trigger_id=trigger["id"], outcome="unavailable", reason="market-mcp unreachable")

    assert len(await store.list_fires_for_trigger(db, trigger_id=trigger["id"], owner_principal=OWNER)) == 1
    assert (
        await store.list_fires_for_trigger(db, trigger_id=trigger["id"], owner_principal=STRANGER) == []
    )


async def test_a_collapsed_fire_carries_how_many_were_skipped(db: asyncpg.Connection) -> None:
    # specs/teams-schedules, "Moduł nie pracował przez sześć godzin".
    schedule = await _schedule(db, next_fire_at=PAST)

    claimed = await store.claim_due_schedule(db, schedule_id=schedule["id"], next_fire_at=FUTURE)
    assert claimed is not None
    fire = await store.record_fire(
        db, schedule_id=schedule["id"], outcome="skipped", reason="daily limit", skipped_count=5
    )

    assert fire["skipped_count"] == 5
