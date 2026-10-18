"""A finished run is handed to the alerts package once. The marker is in the run's own row, written after the alerts package
said yes, so a refusal leaves the run to the next sweep — and a run that finished before the column existed is not news."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import asyncpg
import pytest

from teams import alerts, store
from teams.alerts import RunAnnouncer
from teams.contract import AgentDefinition, CostLimits, TeamDefinition

pytestmark = pytest.mark.db

OWNER = "operator-1"
NOW = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)


class RecordingPublisher:
    def __init__(self, fails: Exception | None = None, refuses_announcing: bool = False) -> None:
        self.fails = fails
        self.refuses_announcing = refuses_announcing
        self.sent: list[tuple[str, dict, str]] = []

    async def announce(self) -> None:
        if self.refuses_announcing:
            raise alerts.Unreachable("no answer")

    async def publish(self, *, source_key: str, attributes: dict, text: str) -> None:
        self.sent.append((source_key, attributes, text))
        if self.fails is not None:
            raise self.fails


async def a_run(db: asyncpg.Connection, status: str, reason: str | None = None, *, finished: datetime = NOW) -> int:
    _, revision = await store.create_team(
        db,
        owner_principal=OWNER,
        name="morning desk",
        description="",
        definition=TeamDefinition(
            agents=[AgentDefinition(key="scout", role="scout", prompt="look", model_id="luna")], limits=CostLimits()
        ),
    )
    run, _ = await store.create_run(db, team_revision_id=revision["id"], owner_principal=OWNER, agent_keys=["scout"])
    await store.mark_run_running(db, run_id=run["id"])
    await store.finish_run(db, run_id=run["id"], status=status, stopped_reason=reason)
    await db.execute("UPDATE runs SET finished_at = $2 WHERE id = $1", run["id"], finished)
    return run["id"]


def announcer(pool, publisher) -> RunAnnouncer:
    return RunAnnouncer(pool, publisher)  # type: ignore[arg-type]


async def test_a_finished_run_is_handed_over_once_with_what_a_rule_filters_by(db, pool) -> None:
    run_id = await a_run(db, "failed", "the run exceeded its time limit")
    publisher = RecordingPublisher()
    sweeping = announcer(pool, publisher)

    assert await sweeping.run(NOW) == 1
    assert await sweeping.run(NOW) == 0

    [(key, attributes, text)] = publisher.sent
    assert key == str(run_id)
    assert (attributes["team"], attributes["status"], attributes["started_by"]) == ("morning desk", "failed", "operator")
    assert "nieudany" in text and "time limit" in text
    assert await db.fetchval("SELECT announced_at FROM runs WHERE id = $1", run_id) == NOW


async def test_a_run_that_started_from_a_schedule_or_a_trigger_says_which(db, pool) -> None:
    run_id = await a_run(db, "completed")
    schedule = await db.fetchval(
        "INSERT INTO schedules (team_id, owner_principal, revision_mode, cron_expression, next_fire_at) "
        "SELECT t.id, $1, 'latest', '*/5 * * * *', now() FROM teams t LIMIT 1 RETURNING id",
        OWNER,
    )
    await db.execute("INSERT INTO schedule_fires (schedule_id, outcome, run_id) VALUES ($1, 'started', $2)", schedule, run_id)
    publisher = RecordingPublisher()

    await announcer(pool, publisher).run(NOW)

    assert publisher.sent[0][1]["started_by"] == "schedule"


async def test_a_refused_run_keeps_no_marker_and_is_tried_again(db, pool) -> None:
    run_id = await a_run(db, "completed")
    sweeping = announcer(pool, RecordingPublisher(fails=alerts.Rejected("no")))

    assert await sweeping.run(NOW) == 0
    assert sweeping.failing is True
    assert await db.fetchval("SELECT announced_at FROM runs WHERE id = $1", run_id) is None

    assert await announcer(pool, RecordingPublisher()).run(NOW) == 1


async def test_a_run_that_is_still_going_is_not_news_and_nothing_is_sent_before_the_type_is_announced(db, pool) -> None:
    _, revision = await store.create_team(
        db,
        owner_principal=OWNER,
        name="live",
        description="",
        definition=TeamDefinition(
            agents=[AgentDefinition(key="scout", role="scout", prompt="look", model_id="luna")], limits=CostLimits()
        ),
    )
    await store.create_run(db, team_revision_id=revision["id"], owner_principal=OWNER, agent_keys=["scout"])
    await a_run(db, "completed")
    publisher = RecordingPublisher(refuses_announcing=True)
    sweeping = announcer(pool, publisher)

    assert await sweeping.run(NOW) == 0 and publisher.sent == []
    publisher.refuses_announcing = False
    assert await sweeping.run(NOW) == 1
    assert [attributes["team"] for _, attributes, _ in publisher.sent] == ["morning desk"]


async def test_a_run_that_finished_longer_ago_than_the_window_is_not_announced_in_a_heap(db, pool) -> None:
    await a_run(db, "completed", finished=NOW - alerts.WINDOW - timedelta(minutes=1))
    publisher = RecordingPublisher()

    assert await announcer(pool, publisher).run(NOW) == 0
    assert publisher.sent == []


async def test_the_runs_that_finished_before_the_marker_existed_are_marked_as_told(postgres_url) -> None:
    """The migration's backfill, run for real: a database at the revision before it, holding a finished run, brought to the
    next one. The first deploy must not announce a backlog."""
    from alembic import command
    from tc_runtime.db import asyncpg_dsn, sqlalchemy_url
    from tc_runtime.migrate import alembic_config

    from teams.runtime import MIGRATIONS

    admin = await asyncpg.connect(asyncpg_dsn(postgres_url))
    try:
        await admin.execute("DROP DATABASE IF EXISTS backfill")
        await admin.execute("CREATE DATABASE backfill")
    finally:
        await admin.close()
    url = postgres_url.rsplit("/", 1)[0] + "/backfill"

    config = alembic_config(MIGRATIONS, sqlalchemy_url(url))
    await asyncio.to_thread(command.upgrade, config, "0009")
    conn = await asyncpg.connect(asyncpg_dsn(url))
    try:
        team = await conn.fetchval("INSERT INTO teams (owner_principal, name, description) VALUES ('o', 'old', '') RETURNING id")
        revision = await conn.fetchval(
            "INSERT INTO team_revisions (team_id, version, definition) VALUES ($1, 1, '{}'::jsonb) RETURNING id", team
        )
        await conn.execute(
            "INSERT INTO runs (team_revision_id, owner_principal, status, finished_at) VALUES ($1, 'o', 'completed', now())",
            revision,
        )
        await asyncio.to_thread(command.upgrade, config, "0010")

        assert await conn.fetchval("SELECT count(*) FROM runs WHERE announced_at IS NULL") == 0
    finally:
        await conn.close()


async def test_a_run_the_alerts_package_refused_does_not_hold_up_the_runs_behind_it(db, pool, monkeypatch) -> None:
    monkeypatch.setattr(alerts, "BATCH", 1)
    await a_run(db, "completed", finished=NOW - timedelta(minutes=2))
    await a_run(db, "failed", "boom", finished=NOW - timedelta(minutes=1))

    class RefusesTheFirst(RecordingPublisher):
        async def publish(self, *, source_key: str, attributes: dict, text: str) -> None:
            await super().publish(source_key=source_key, attributes=attributes, text=text)
            if len(self.sent) == 1:
                raise alerts.Rejected("does not fit")

    publisher = RefusesTheFirst()
    sweeping = announcer(pool, publisher)

    assert await sweeping.run(NOW) == 0
    assert await sweeping.run(NOW + timedelta(seconds=15)) == 1
    assert len({key for key, _, _ in publisher.sent}) == 2


def test_no_alerts_package_builds_no_announcer(pool) -> None:
    assert alerts.build(pool, None) is None
