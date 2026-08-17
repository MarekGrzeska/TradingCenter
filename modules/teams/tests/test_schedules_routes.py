"""Schedules and triggers over HTTP — the wire shapes, the refusals, and who sees what.

Through `TestClient` and the real lifespan, like `test_catalogue_routes.py`: the routes
read the pool and the settings the lifespan puts on `app.state`, so a test that assembled
its own app would be testing a second arrangement rather than the one deployed.

Fire history is written directly through `store.py` in these tests rather than through a
route — starting the clock that claims a due fire and writes the history row is group 3's
job (`scheduler/`), not these routes'. What is proven here is that the row, once it
exists, is exactly what an operator sees.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import asyncpg
import pytest
from fastapi.testclient import TestClient

from teams import store
from teams.app import app
from teams.db import asyncpg_dsn

from .mcp_stand_in import serving_sync

pytestmark = pytest.mark.db

MODEL_ID = "gpt-5.6-luna"

_ENV = {
    "OPENAI_API_KEY": "key",
    "MODELS": (
        f'[{{"id":"{MODEL_ID}","model":"luna-prod","display_name":"Luna",'
        '"cost_rank":1,"input_rate_per_1m":"1","output_rate_per_1m":"6"}]'
    ),
}

OWNER = {"X-MS-CLIENT-PRINCIPAL-ID": "operator-1"}
STRANGER = {"X-MS-CLIENT-PRINCIPAL-ID": "operator-2"}


@pytest.fixture(autouse=True)
def _env(migrated_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", migrated_url)
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)


@pytest.fixture
def client(db: asyncpg.Connection) -> Iterator[TestClient]:
    """No tool server configured — enough for every schedule test, and for the trigger
    refusals that do not need one to answer."""
    with TestClient(app) as started:
        yield started


def _record_fire(migrated_url: str, **kwargs) -> asyncpg.Record:
    """A row written the way group 3's clock will write it, without needing the clock —
    a fresh connection outside the app's own pool, closed before the assertion reads it
    back through the route."""

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


# --- schedules ------------------------------------------------------------------------


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


# --- triggers -----------------------------------------------------------------------


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


# --- specs/teams-schedules, "Harmonogram nad rewizją z narzędziami zapisującymi wymaga
# jawnego potwierdzenia" — over HTTP, against a server that really announces a write tool.
# The check used to consult a hand-kept list of dangerous names that was empty for the
# whole of phase 2, so these three are what stop it going quiet again.


def test_a_schedule_over_a_revision_carrying_a_write_tool_is_refused_without_the_ack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with serving_sync(tools=("place_order",)) as url:
        monkeypatch.setenv("TRADING_MCP_URL", url)
        with TestClient(app) as started:
            team_id, revision_id = _team(started, tools=["place_order"])
            response = started.post(
                f"/teams/{team_id}/schedules", json=_schedule_body(revision_id), headers=OWNER
            )

    assert response.status_code == 422, response.text
    assert "place_order" in response.text
    assert "unattended_ack" in response.text


def test_the_same_schedule_is_accepted_when_the_operator_acknowledges_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with serving_sync(tools=("place_order",)) as url:
        monkeypatch.setenv("TRADING_MCP_URL", url)
        with TestClient(app) as started:
            team_id, revision_id = _team(started, tools=["place_order"])
            response = started.post(
                f"/teams/{team_id}/schedules",
                json=_schedule_body(revision_id) | {"unattended_ack": True},
                headers=OWNER,
            )

    assert response.status_code == 201, response.text
    assert response.json()["unattended_ack"] is True


def test_a_schedule_over_a_revision_carrying_only_read_tools_needs_no_ack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with serving_sync(tools=("read_indicators",)) as url:
        monkeypatch.setenv("MARKET_MCP_URL", url)
        with TestClient(app) as started:
            team_id, revision_id = _team(started, tools=["read_indicators"])
            response = started.post(
                f"/teams/{team_id}/schedules", json=_schedule_body(revision_id), headers=OWNER
            )

    assert response.status_code == 201, response.text
    assert response.json()["unattended_ack"] is False


def test_a_trigger_over_a_revision_carrying_a_write_tool_is_refused_without_the_ack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The trigger half of the same rule (specs/teams-triggers, "Wyzwalacz podlega tym
    samym granicom co harmonogram") — one snapshot answers both checks, and the condition's
    own tool being a read one does not excuse what the *revision* carries."""
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

    assert response.status_code == 422, response.text
    assert "place_order" in response.text
