"""`GET /usage` and the daily ceiling, over HTTP — the two halves an operator meets."""

from __future__ import annotations

from collections.abc import Iterator

import asyncpg
import pytest
from fastapi.testclient import TestClient

from workbench.app import app

from .scripted_provider import ScriptedProvider, says
from .waiting import wait_for_status

pytestmark = pytest.mark.db

MODEL_ID = "gpt-5.6-luna"
DEAR_MODEL_ID = "gpt-5.6-sol"

_ENV = {
    "TEAMS_OPENAI_API_KEY": "key",
    "TEAMS_MODELS": (
        f'[{{"id":"{MODEL_ID}","model":"luna-prod","display_name":"Luna",'
        '"cost_rank":1,"input_rate_per_1m":"1","output_rate_per_1m":"6"},'
        f'{{"id":"{DEAR_MODEL_ID}","model":"sol-prod","display_name":"Sol",'
        '"cost_rank":2,"input_rate_per_1m":"10","output_rate_per_1m":"60"}]'
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
    with TestClient(app) as started:
        app.state.teams.provider = ScriptedProvider(default=says("done."))
        yield started


def _agent(key: str, model_id: str = MODEL_ID) -> dict:
    return {
        "key": key,
        "role": key,
        "prompt": f"be the {key}",
        "model_id": model_id,
        "tools": [],
    }


def _team(client: TestClient, agents: list[dict], edges: list[dict] | None = None, limits: dict | None = None) -> int:
    definition: dict = {"agents": agents, "edges": edges or []}
    if limits is not None:
        definition["limits"] = limits
    response = client.post(
        "/teams", json={"name": "a team", "description": "", "definition": definition}, headers=OWNER
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _run_to_the_end(client: TestClient, team_id: int) -> int:
    started = client.post(f"/teams/{team_id}/runs", headers=OWNER)
    assert started.status_code == 201, started.text
    run_id = started.json()["id"]
    wait_for_status(client, run_id, headers=OWNER)
    return run_id


def test_usage_is_broken_down_so_a_cost_can_be_put_on_a_role(client: TestClient) -> None:
    """specs/teams-usage, "Odczyt zużycia w rozbiciu na role"."""
    team_id = _team(
        client,
        [_agent("scout"), _agent("judge", DEAR_MODEL_ID)],
        [{"from": "scout", "to": "judge"}],
    )
    run_id = _run_to_the_end(client, team_id)

    usage = client.get("/teams/usage", params={"run_id": run_id}, headers=OWNER).json()

    by_agent = {row["key"]: row for row in usage["by_agent"]}
    assert set(by_agent) == {"scout", "judge"}
    assert by_agent["scout"]["input_tokens"] == 100
    assert by_agent["scout"]["output_tokens"] == 20
    # The dear model costs ten times the cheap one for the same tokens, which is the whole
    # reason a team picks a model per agent.
    assert float(by_agent["judge"]["cost"]) == pytest.approx(float(by_agent["scout"]["cost"]) * 10)

    by_model = {row["key"]: row for row in usage["by_model"]}
    assert set(by_model) == {MODEL_ID, DEAR_MODEL_ID}
    assert float(usage["total_cost"]) == pytest.approx(
        float(by_agent["scout"]["cost"]) + float(by_agent["judge"]["cost"])
    )


def test_usage_of_one_run_is_not_the_usage_of_another(client: TestClient) -> None:
    team_id = _team(client, [_agent("scout")])
    first = _run_to_the_end(client, team_id)
    second = _run_to_the_end(client, team_id)

    one = client.get("/teams/usage", params={"run_id": first}, headers=OWNER).json()
    both = client.get("/teams/usage", params={"team_id": team_id}, headers=OWNER).json()

    assert float(both["total_cost"]) == pytest.approx(float(one["total_cost"]) * 2)
    assert second != first


def test_a_call_the_provider_reported_nothing_for_is_counted_as_unknown(
    client: TestClient,
) -> None:
    """specs/teams-usage, "Model nie zwrócił liczby tokenów" — the row exists, the cost is
    absent rather than zero, and the summary says how many such rows it is missing."""
    app.state.teams.provider = ScriptedProvider(default=says("done.", tokens=None))
    team_id = _team(client, [_agent("scout")])
    run_id = _run_to_the_end(client, team_id)

    usage = client.get("/teams/usage", params={"run_id": run_id}, headers=OWNER).json()

    assert usage["total_cost"] == "0"
    assert usage["by_agent"][0]["unknown_count"] == 1
    assert usage["by_agent"][0]["input_tokens"] == 0


def test_a_stranger_sees_none_of_it(client: TestClient) -> None:
    team_id = _team(client, [_agent("scout")])
    run_id = _run_to_the_end(client, team_id)

    usage = client.get("/teams/usage", params={"run_id": run_id}, headers=STRANGER).json()

    # Empty, not 404: this is an aggregate, and "no rows" is the only answer that does not
    # tell a stranger the run exists (specs/teams-browser-access).
    assert usage == {"total_cost": "0", "by_agent": [], "by_model": []}


def test_a_team_that_used_up_its_day_cannot_start_another_run(client: TestClient) -> None:
    """specs/teams-usage, "Zespół wyczerpał granicę dobową"."""
    team_id = _team(client, [_agent("scout")], limits={"daily_limit": "0.0002"})
    _run_to_the_end(client, team_id)  # spends 0.00022, which is over the limit

    refused = client.post(f"/teams/{team_id}/runs", headers=OWNER)

    assert refused.status_code == 422
    assert "daily cost limit" in refused.text
    assert "0.0002" in refused.text
    # And nothing was created for it.
    assert len(client.get(f"/teams/{team_id}/runs", headers=OWNER).json()) == 1


def test_a_daily_limit_with_room_left_starts_the_run(client: TestClient) -> None:
    team_id = _team(client, [_agent("scout")], limits={"daily_limit": "1"})
    _run_to_the_end(client, team_id)

    second = client.post(f"/teams/{team_id}/runs", headers=OWNER)

    assert second.status_code == 201
