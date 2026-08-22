"""A team's memory over HTTP — what the operator sees and what they may remove.

Through `TestClient` and the real lifespan, like the catalogue's own route tests: these
routes read the pool the lifespan puts on `app.state`, so a test assembling its own app
would be testing a second arrangement rather than the deployed one.
"""

from __future__ import annotations

from collections.abc import Iterator

import asyncpg
import pytest
from fastapi.testclient import TestClient

from teams import store
from teams.contract import MEMORY_READ_LIMIT
from workbench.app import app

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
    with TestClient(app) as started:
        yield started


def _definition() -> dict:
    return {
        "agents": [
            {
                "key": "scout",
                "role": "the scout",
                "prompt": "say something",
                "model_id": MODEL_ID,
                "tools": [],
            }
        ],
        "edges": [],
    }


def _team(client: TestClient, *, headers: dict = OWNER) -> int:
    response = client.post(
        "/teams",
        json={"name": "morning desk", "description": "", "definition": _definition()},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()["id"]


async def _remember(
    db: asyncpg.Connection, team_id: int, content: str, *, owner: str = "operator-1"
) -> int:
    row = await store.add_memory(
        db,
        team_id=team_id,
        owner_principal=owner,
        author_agent_key="scout",
        run_id=None,
        content=content,
    )
    assert row is not None
    return row["id"]


async def test_the_operator_reads_their_teams_memory_newest_first(
    client: TestClient, db: asyncpg.Connection
) -> None:
    team_id = _team(client)
    for content in ("older", "newer"):
        await _remember(db, team_id, content)

    body = client.get(f"/teams/{team_id}/memory", headers=OWNER).json()

    assert [entry["content"] for entry in body["entries"]] == ["newer", "older"]
    assert body["total"] == 2
    assert body["entries"][0]["author_agent_key"] == "scout"


async def test_a_team_that_remembered_nothing_answers_empty_not_missing(
    client: TestClient,
) -> None:
    team_id = _team(client)

    response = client.get(f"/teams/{team_id}/memory", headers=OWNER)

    assert response.status_code == 200
    assert response.json() == {"entries": [], "total": 0}


async def test_the_read_is_capped_and_says_how_much_there_is(
    client: TestClient, db: asyncpg.Connection
) -> None:
    team_id = _team(client)
    for index in range(MEMORY_READ_LIMIT + 2):
        await _remember(db, team_id, f"note {index}")

    body = client.get(f"/teams/{team_id}/memory", headers=OWNER).json()

    assert len(body["entries"]) == MEMORY_READ_LIMIT
    assert body["total"] == MEMORY_READ_LIMIT + 2


def test_a_team_that_does_not_exist_is_a_404(client: TestClient) -> None:
    assert client.get("/teams/999999/memory", headers=OWNER).status_code == 404


async def test_somebody_elses_memory_reads_like_a_team_that_is_not_there(
    client: TestClient, db: asyncpg.Connection
) -> None:
    # specs/teams-memory: indistinguishable from a team that does not exist.
    team_id = _team(client)
    await _remember(db, team_id, "mine")

    assert client.get(f"/teams/{team_id}/memory", headers=STRANGER).status_code == 404


async def test_the_operator_deletes_one_entry(
    client: TestClient, db: asyncpg.Connection
) -> None:
    team_id = _team(client)
    await _remember(db, team_id, "keep me")
    doomed = await _remember(db, team_id, "delete me")

    response = client.delete(f"/teams/{team_id}/memory/{doomed}", headers=OWNER)

    assert response.status_code == 204
    body = client.get(f"/teams/{team_id}/memory", headers=OWNER).json()
    assert [entry["content"] for entry in body["entries"]] == ["keep me"]


async def test_a_stranger_cannot_delete_an_entry(
    client: TestClient, db: asyncpg.Connection
) -> None:
    team_id = _team(client)
    entry_id = await _remember(db, team_id, "mine")

    response = client.delete(f"/teams/{team_id}/memory/{entry_id}", headers=STRANGER)

    assert response.status_code == 404
    assert client.get(f"/teams/{team_id}/memory", headers=OWNER).json()["total"] == 1


def test_deleting_an_entry_that_is_not_there_is_a_404(client: TestClient) -> None:
    team_id = _team(client)

    assert client.delete(f"/teams/{team_id}/memory/999999", headers=OWNER).status_code == 404


async def test_there_is_no_route_that_writes_a_memory_entry(client: TestClient) -> None:
    """An entry is an agent's decision, never the operator's — the only writer is the tool
    (specs/teams-memory, "Wpis powstaje decyzją agenta")."""
    team_id = _team(client)

    response = client.post(
        f"/teams/{team_id}/memory", json={"content": "by hand"}, headers=OWNER
    )

    assert response.status_code == 405
