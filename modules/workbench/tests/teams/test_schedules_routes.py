"""Schedules and triggers over HTTP — the wire shapes, the refusals, and who sees what. Through `TestClient`
and the real lifespan, like the catalogue's own route tests.

Fire history is written directly through `store` here rather than through a route: claiming a due fire is
the clock's job. What is proven is that the row, once it exists, is exactly what an operator sees."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import datetime
from zoneinfo import ZoneInfo

import asyncpg
import pytest
from fastapi.testclient import TestClient
from tc_runtime.db import asyncpg_dsn

from teams import store
from workbench.app import app

from .mcp_stand_in import serving_sync

pytestmark = pytest.mark.db

MODEL_ID = "gpt-5.6-luna"

_ENV = {
    "TEAMS_OPENAI_API_KEY": "key",
    "TEAMS_MODELS": (
        f'[{{"id":"{MODEL_ID}","model":"luna-prod","display_name":"Luna",'
        '"cost_rank":1,"input_rate_per_1m":"1","output_rate_per_1m":"6"}]'
    ),
}

OWNER = {"X-MS-CLIENT-PRINCIPAL-ID": "operator-1"}
STRANGER = {"X-MS-CLIENT-PRINCIPAL-ID": "operator-2"}


@pytest.fixture(autouse=True)
def _env(workbench_env: None, migrated_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)


@pytest.fixture
def client(db: asyncpg.Connection) -> Iterator[TestClient]:
    """No tool server configured — enough for every schedule test, and for the trigger
    refusals that do not need one to answer."""
    with TestClient(app) as started:
        yield started


def _record_fire(migrated_url: str, **kwargs) -> asyncpg.Record:
    """A row written the way the clock will write it, without needing the clock — a fresh connection outside
    the app's own pool, closed before the assertion reads it back through the route."""

    async def _write() -> asyncpg.Record:
        conn = await asyncpg.connect(asyncpg_dsn(migrated_url))
        try:
            return await store.record_fire(conn, **kwargs)
        finally:
            await conn.close()

    return asyncio.run(_write())


def _definition(*, tools: list[str] | None = None) -> dict:
    return {
        "agents": [
            {
                "key": "scout",
                "role": "scout",
                "prompt": "read the market",
                "model_id": MODEL_ID,
                "tools": tools or [],
            }
        ],
        "edges": [],
    }


def _team(client: TestClient, *, headers: dict = OWNER, tools: list[str] | None = None) -> tuple[int, int]:
    created = client.post(
        "/teams",
        json={"name": "morning desk", "description": "", "definition": _definition(tools=tools)},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    team_id = created.json()["id"]
    revision = client.get(f"/teams/{team_id}/revisions/latest", headers=headers).json()
    return team_id, revision["id"]


def _schedule_body(revision_id: int, *, cron: str = "*/5 * * * *") -> dict:
    return {"revision_mode": "pinned", "pinned_revision_id": revision_id, "cron_expression": cron}


def _trigger_body(revision_id: int, *, tool_name: str = "read_indicators") -> dict:
    return {
        "revision_mode": "pinned",
        "pinned_revision_id": revision_id,
        "tool_name": tool_name,
        "arguments": {"symbol": "US100"},
        "field_path": "rsi",
        "comparison": "gt",
        "threshold": "70",
    }



def test_a_schedule_is_created_with_a_next_fire_computed_from_the_cron_expression(
    client: TestClient,
) -> None:
    team_id, revision_id = _team(client)

    response = client.post(f"/teams/{team_id}/schedules", json=_schedule_body(revision_id), headers=OWNER)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["cron_expression"] == "*/5 * * * *"
    assert body["enabled"] is True
    assert body["consecutive_failures"] == 0
    assert body["next_fire_at"] is not None


def test_an_invalid_cron_expression_is_refused(client: TestClient) -> None:
    team_id, revision_id = _team(client)

    response = client.post(
        f"/teams/{team_id}/schedules",
        json=_schedule_body(revision_id, cron="not a cron expression"),
        headers=OWNER,
    )

    assert response.status_code == 422


def test_a_pinned_revision_from_another_team_is_refused(client: TestClient) -> None:
    team_id, _ = _team(client)
    _, other_revision_id = _team(client)  # a second team, same owner

    response = client.post(
        f"/teams/{team_id}/schedules",
        json=_schedule_body(other_revision_id),
        headers=OWNER,
    )

    assert response.status_code == 422
    assert str(other_revision_id) in response.text


def test_a_schedule_tracking_latest_carries_no_pinned_revision(client: TestClient) -> None:
    team_id, _ = _team(client)

    created = client.post(
        f"/teams/{team_id}/schedules",
        json={"revision_mode": "latest", "cron_expression": "0 9 * * MON-FRI"},
        headers=OWNER,
    )

    assert created.status_code == 201, created.text
    assert created.json()["pinned_revision_id"] is None


def test_updating_a_schedule_changes_its_cron_expression(client: TestClient) -> None:
    team_id, revision_id = _team(client)
    schedule_id = client.post(
        f"/teams/{team_id}/schedules", json=_schedule_body(revision_id), headers=OWNER
    ).json()["id"]

    updated = client.put(
        f"/schedules/{schedule_id}",
        json=_schedule_body(revision_id, cron="0 9 * * MON-FRI"),
        headers=OWNER,
    )

    assert updated.status_code == 200, updated.text
    assert updated.json()["cron_expression"] == "0 9 * * MON-FRI"


def test_disabling_and_re_enabling_a_schedule(client: TestClient) -> None:
    team_id, revision_id = _team(client)
    schedule_id = client.post(
        f"/teams/{team_id}/schedules", json=_schedule_body(revision_id), headers=OWNER
    ).json()["id"]

    disabled = client.post(f"/schedules/{schedule_id}/disable", headers=OWNER)
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False

    enabled = client.post(f"/schedules/{schedule_id}/enable", headers=OWNER)
    assert enabled.status_code == 200
    assert enabled.json()["enabled"] is True


def test_next_fires_preview_returns_the_requested_count_in_order(client: TestClient) -> None:
    team_id, revision_id = _team(client)
    schedule_id = client.post(
        f"/teams/{team_id}/schedules", json=_schedule_body(revision_id), headers=OWNER
    ).json()["id"]

    preview = client.get(f"/schedules/{schedule_id}/next-fires", params={"count": 3}, headers=OWNER)

    assert preview.status_code == 200
    times = preview.json()["times"]
    assert len(times) == 3
    assert times == sorted(times)


def test_a_schedule_saved_as_a_rhythm_comes_back_as_the_same_rhythm(client: TestClient) -> None:
    team_id, revision_id = _team(client)

    created = client.post(
        f"/teams/{team_id}/schedules",
        json={
            "revision_mode": "pinned",
            "pinned_revision_id": revision_id,
            "recurrence": {"kind": "daily", "hour": 9, "minute": 0},
        },
        headers=OWNER,
    )

    assert created.status_code == 201, created.text
    body = created.json()
    assert body["cron_expression"] == "0 9 * * *"
    assert body["recurrence"] == {
        "kind": "daily",
        "hour": 9,
        "minute": 0,
        "minutes": None,
        "weekdays": None,
        "day_of_month": None,
    }


def test_an_hourly_rhythm_carries_the_days_it_was_saved_with(client: TestClient) -> None:
    """What the operator asked for: every hour on the days the market is open."""
    team_id, revision_id = _team(client)

    created = client.post(
        f"/teams/{team_id}/schedules",
        json={
            "revision_mode": "pinned",
            "pinned_revision_id": revision_id,
            "recurrence": {"kind": "hourly", "minute": 35, "weekdays": [1, 2, 3, 4, 5]},
        },
        headers=OWNER,
    )

    assert created.status_code == 201, created.text
    body = created.json()
    assert body["cron_expression"] == "35 * * * 1,2,3,4,5"
    assert body["recurrence"]["kind"] == "hourly"
    assert body["recurrence"]["weekdays"] == [1, 2, 3, 4, 5]


def test_a_daily_rhythm_with_weekdays_is_refused(client: TestClient) -> None:
    """It is `weekly`'s own expression, and one expression may only have one rhythm."""
    team_id, revision_id = _team(client)

    refused = client.post(
        f"/teams/{team_id}/schedules",
        json={
            "revision_mode": "pinned",
            "pinned_revision_id": revision_id,
            "recurrence": {"kind": "daily", "hour": 9, "minute": 0, "weekdays": [1, 2, 3, 4, 5]},
        },
        headers=OWNER,
    )

    assert refused.status_code == 422
    assert "weekly" in refused.text


def test_a_rhythm_with_weekdays_can_be_previewed_before_it_is_saved(client: TestClient) -> None:
    """That the days survive the draft route. The weekend itself is proven where the arithmetic lives; this
    preview caps at 20 fires, which for an hourly rhythm need not reach a Saturday."""
    preview = client.post(
        "/schedules/next-fires",
        json={
            "recurrence": {"kind": "hourly", "minute": 35, "weekdays": [1, 2, 3, 4, 5]},
            "count": 20,
        },
        headers=OWNER,
    )

    assert preview.status_code == 200, preview.text
    times = preview.json()["times"]
    assert len(times) == 20
    # Read as the Polish wall clock the operator set them in, not as UTC: a Saturday moment
    # is a Saturday to them whichever side of midnight UTC it falls on.
    days = {
        datetime.fromisoformat(time).astimezone(ZoneInfo("Europe/Warsaw")).isoweekday()
        for time in times
    }
    assert days <= {1, 2, 3, 4, 5}


def test_a_schedule_saved_as_an_expression_outside_the_rhythms_carries_no_rhythm(
    client: TestClient,
) -> None:
    team_id, revision_id = _team(client)

    created = client.post(
        f"/teams/{team_id}/schedules",
        json=_schedule_body(revision_id, cron="0 9 * * MON-FRI"),
        headers=OWNER,
    )

    assert created.status_code == 201, created.text
    assert created.json()["recurrence"] is None


def test_a_schedule_must_name_its_timing_exactly_once(client: TestClient) -> None:
    team_id, revision_id = _team(client)
    both = {
        "revision_mode": "pinned",
        "pinned_revision_id": revision_id,
        "cron_expression": "0 9 * * *",
        "recurrence": {"kind": "daily", "hour": 9, "minute": 0},
    }
    neither = {"revision_mode": "pinned", "pinned_revision_id": revision_id}

    assert client.post(f"/teams/{team_id}/schedules", json=both, headers=OWNER).status_code == 422
    assert client.post(f"/teams/{team_id}/schedules", json=neither, headers=OWNER).status_code == 422


def test_next_fires_are_previewed_for_a_draft_nobody_saved(client: TestClient) -> None:
    preview = client.post(
        "/schedules/next-fires",
        json={"recurrence": {"kind": "daily", "hour": 9, "minute": 0}, "count": 3},
        headers=OWNER,
    )

    assert preview.status_code == 200, preview.text
    times = preview.json()["times"]
    assert len(times) == 3
    assert times == sorted(times)
    # 9:00 in Poland — 07:00 UTC in summer, 08:00 in winter, and nothing else.
    assert {time[11:16] for time in times} <= {"07:00", "08:00"}


def test_a_draft_that_cannot_be_run_is_refused_rather_than_previewed(client: TestClient) -> None:
    refused = client.post(
        "/schedules/next-fires",
        json={"cron_expression": "not a cron expression"},
        headers=OWNER,
    )

    assert refused.status_code == 422


def test_a_stranger_gets_404_for_a_schedule_that_is_not_theirs(client: TestClient) -> None:
    team_id, revision_id = _team(client)
    schedule_id = client.post(
        f"/teams/{team_id}/schedules", json=_schedule_body(revision_id), headers=OWNER
    ).json()["id"]

    assert client.get(f"/schedules/{schedule_id}", headers=STRANGER).status_code == 404
    assert client.post(f"/schedules/{schedule_id}/disable", headers=STRANGER).status_code == 404
    assert client.get(f"/teams/{team_id}/schedules", headers=STRANGER).status_code == 404


def test_a_fire_that_started_nothing_shows_up_in_the_schedules_history(
    client: TestClient, migrated_url: str
) -> None:
    team_id, revision_id = _team(client)
    schedule_id = client.post(
        f"/teams/{team_id}/schedules", json=_schedule_body(revision_id), headers=OWNER
    ).json()["id"]

    _record_fire(
        migrated_url,
        schedule_id=schedule_id,
        outcome="skipped",
        reason="the previous run is still working",
    )

    history = client.get(f"/schedules/{schedule_id}/fires", headers=OWNER)

    assert history.status_code == 200
    rows = history.json()
    assert len(rows) == 1
    assert rows[0]["outcome"] == "skipped"
    assert rows[0]["run_id"] is None
    assert rows[0]["reason"] == "the previous run is still working"



def test_a_trigger_with_no_tool_server_configured_is_refused(client: TestClient) -> None:
    team_id, revision_id = _team(client)

    response = client.post(
        f"/teams/{team_id}/triggers", json=_trigger_body(revision_id), headers=OWNER
    )

    assert response.status_code == 422
    assert "MARKET_MCP_URL" in response.text


def test_a_trigger_naming_an_unannounced_tool_is_refused(
    client: TestClient, migrated_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    with serving_sync(tools=("read_indicators",)) as url:
        monkeypatch.setenv("MARKET_MCP_URL", url)
        with TestClient(app) as started:
            team_id, revision_id = _team(started)
            response = started.post(
                f"/teams/{team_id}/triggers",
                json=_trigger_body(revision_id, tool_name="get_last_price"),
                headers=OWNER,
            )

    assert response.status_code == 422
    assert "get_last_price" in response.text


def test_a_trigger_naming_an_announced_tool_is_created(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    with serving_sync(tools=("read_indicators",)) as url:
        monkeypatch.setenv("MARKET_MCP_URL", url)
        with TestClient(app) as started:
            team_id, revision_id = _team(started)
            response = started.post(
                f"/teams/{team_id}/triggers", json=_trigger_body(revision_id), headers=OWNER
            )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["tool_name"] == "read_indicators"
    # NUMERIC(18, 8) on the wire, same precision as every other rate on this contract.
    assert body["threshold"] == "70.00000000"
    assert body["last_result"] is None
    assert body["last_fired_at"] is None


def test_updating_a_trigger_changes_its_condition(monkeypatch: pytest.MonkeyPatch) -> None:
    with serving_sync(tools=("read_indicators",)) as url:
        monkeypatch.setenv("MARKET_MCP_URL", url)
        with TestClient(app) as started:
            team_id, revision_id = _team(started)
            trigger_id = started.post(
                f"/teams/{team_id}/triggers", json=_trigger_body(revision_id), headers=OWNER
            ).json()["id"]

            response = started.put(
                f"/triggers/{trigger_id}",
                json=_trigger_body(revision_id, tool_name="read_indicators") | {"threshold": "55"},
                headers=OWNER,
            )

    assert response.status_code == 200, response.text
    assert response.json()["threshold"] == "55.00000000"


def test_disabling_and_re_enabling_a_trigger(monkeypatch: pytest.MonkeyPatch) -> None:
    with serving_sync(tools=("read_indicators",)) as url:
        monkeypatch.setenv("MARKET_MCP_URL", url)
        with TestClient(app) as started:
            team_id, revision_id = _team(started)
            trigger_id = started.post(
                f"/teams/{team_id}/triggers", json=_trigger_body(revision_id), headers=OWNER
            ).json()["id"]

            disabled = started.post(f"/triggers/{trigger_id}/disable", headers=OWNER)
            assert disabled.status_code == 200
            assert disabled.json()["enabled"] is False

            enabled = started.post(f"/triggers/{trigger_id}/enable", headers=OWNER)

    assert enabled.status_code == 200
    assert enabled.json()["enabled"] is True


def test_a_fire_that_started_nothing_shows_up_in_the_triggers_history(
    migrated_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    with serving_sync(tools=("read_indicators",)) as url:
        monkeypatch.setenv("MARKET_MCP_URL", url)
        with TestClient(app) as started:
            team_id, revision_id = _team(started)
            trigger_id = started.post(
                f"/teams/{team_id}/triggers", json=_trigger_body(revision_id), headers=OWNER
            ).json()["id"]

            _record_fire(
                migrated_url,
                trigger_id=trigger_id,
                outcome="unavailable",
                reason="market-mcp unreachable",
            )

            history = started.get(f"/triggers/{trigger_id}/fires", headers=OWNER)

    assert history.status_code == 200
    rows = history.json()
    assert len(rows) == 1
    assert rows[0]["outcome"] == "unavailable"
    assert rows[0]["run_id"] is None


# Four tests stood here, holding a schedule over an order-placing revision to a consent field. The
# requirement is withdrawn, so what is held now is the opposite: the same save goes through.


def test_a_schedule_over_order_placing_tools_is_written_without_any_consent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with serving_sync(tools=("place_order",)) as url:
        monkeypatch.setenv("TRADING_MCP_URL", url)
        with TestClient(app) as started:
            team_id, revision_id = _team(started, tools=["place_order"])
            response = started.post(
                f"/teams/{team_id}/schedules", json=_schedule_body(revision_id), headers=OWNER
            )

    assert response.status_code == 201, response.text
    assert "unattended_ack" not in response.json()


def test_a_trigger_over_order_placing_tools_is_written_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with (
        serving_sync(tools=("read_indicators",)) as market_url,
        serving_sync(tools=("place_order",)) as trading_url,
    ):
        monkeypatch.setenv("MARKET_MCP_URL", market_url)
        monkeypatch.setenv("TRADING_MCP_URL", trading_url)
        with TestClient(app) as started:
            team_id, revision_id = _team(started, tools=["place_order"])
            response = started.post(
                f"/teams/{team_id}/triggers", json=_trigger_body(revision_id), headers=OWNER
            )

    assert response.status_code == 201, response.text


def test_an_acknowledgement_field_from_an_older_terminal_is_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The window between deploying this module and deploying the terminal. A terminal built before this
    change still sends `unattended_ack`, and the module must drop it rather than refuse the save."""
    with serving_sync(tools=("place_order",)) as url:
        monkeypatch.setenv("TRADING_MCP_URL", url)
        with TestClient(app) as started:
            team_id, revision_id = _team(started, tools=["place_order"])
            response = started.post(
                f"/teams/{team_id}/schedules",
                json=_schedule_body(revision_id) | {"unattended_ack": False},
                headers=OWNER,
            )

    assert response.status_code == 201, response.text
    assert "unattended_ack" not in response.json()



def test_a_deleted_schedule_is_gone_from_the_catalogue(client: TestClient) -> None:
    team_id, revision_id = _team(client)
    schedule_id = client.post(
        f"/teams/{team_id}/schedules", json=_schedule_body(revision_id), headers=OWNER
    ).json()["id"]

    removed = client.delete(f"/schedules/{schedule_id}", headers=OWNER)

    assert removed.status_code == 204
    assert client.get(f"/schedules/{schedule_id}", headers=OWNER).status_code == 404
    assert client.get(f"/teams/{team_id}/schedules", headers=OWNER).json() == []
    # Twice is not an error the second time round, it is the same 404 as never having
    # existed — there is no third state to report.
    assert client.delete(f"/schedules/{schedule_id}", headers=OWNER).status_code == 404


def test_deleting_a_schedule_takes_its_fire_history(client: TestClient, migrated_url: str) -> None:
    """The cascade from `0007`, seen from the route: without it this delete fails outright
    against the foreign key, because a fire row may name neither a schedule nor a trigger."""
    team_id, revision_id = _team(client)
    schedule_id = client.post(
        f"/teams/{team_id}/schedules", json=_schedule_body(revision_id), headers=OWNER
    ).json()["id"]
    _record_fire(
        migrated_url,
        schedule_id=schedule_id,
        outcome="skipped",
        reason="the previous run is still working",
    )
    assert len(client.get(f"/schedules/{schedule_id}/fires", headers=OWNER).json()) == 1

    assert client.delete(f"/schedules/{schedule_id}", headers=OWNER).status_code == 204

    assert client.get(f"/schedules/{schedule_id}/fires", headers=OWNER).status_code == 404


def test_a_strangers_schedule_is_neither_deleted_nor_admitted_to(client: TestClient) -> None:
    team_id, revision_id = _team(client)
    schedule_id = client.post(
        f"/teams/{team_id}/schedules", json=_schedule_body(revision_id), headers=OWNER
    ).json()["id"]

    assert client.delete(f"/schedules/{schedule_id}", headers=STRANGER).status_code == 404
    assert client.get(f"/schedules/{schedule_id}", headers=OWNER).status_code == 200


def test_disabling_is_not_deleting(client: TestClient) -> None:
    """Two words for two things, and the list is where the difference shows: a disabled
    schedule is still there, with its reason, and comes back on."""
    team_id, revision_id = _team(client)
    schedule_id = client.post(
        f"/teams/{team_id}/schedules", json=_schedule_body(revision_id), headers=OWNER
    ).json()["id"]

    assert client.post(f"/schedules/{schedule_id}/disable", headers=OWNER).status_code == 200

    assert client.get(f"/schedules/{schedule_id}", headers=OWNER).json()["enabled"] is False
    assert len(client.get(f"/teams/{team_id}/schedules", headers=OWNER).json()) == 1
    assert client.post(f"/schedules/{schedule_id}/enable", headers=OWNER).json()["enabled"] is True


def test_a_deleted_trigger_is_gone_with_its_history(
    monkeypatch: pytest.MonkeyPatch, migrated_url: str
) -> None:
    """A trigger needs a server that announces its condition's tool, so this one builds its
    own rather than borrowing the shared client."""
    with serving_sync(tools=("read_indicators",)) as url:
        monkeypatch.setenv("MARKET_MCP_URL", url)
        with TestClient(app) as started:
            team_id, revision_id = _team(started, tools=["read_indicators"])
            trigger_id = started.post(
                f"/teams/{team_id}/triggers", json=_trigger_body(revision_id), headers=OWNER
            ).json()["id"]
            _record_fire(
                migrated_url, trigger_id=trigger_id, outcome="skipped", reason="cooling down"
            )

            assert started.delete(f"/triggers/{trigger_id}", headers=STRANGER).status_code == 404
            assert started.delete(f"/triggers/{trigger_id}", headers=OWNER).status_code == 204
            assert started.get(f"/triggers/{trigger_id}", headers=OWNER).status_code == 404


