"""The catalogue over HTTP — the wire shapes, the refusals and who sees what. Through `TestClient` and the
real lifespan: a test that assembled its own app would be testing a second arrangement."""

from __future__ import annotations

from collections.abc import Iterator

import asyncpg
import pytest
from fastapi.testclient import TestClient

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
    """`db` is depended on for its truncation, not for the connection — every test here
    starts against an empty catalogue."""
    with TestClient(app) as started:
        yield started


def _agent(key: str, *, tools: list[str] | None = None, model_id: str = MODEL_ID) -> dict:
    return {
        "key": key,
        "role": f"the {key}",
        "prompt": "say something",
        "model_id": model_id,
        "tools": tools or [],
    }


def _definition(agents: list[dict] | None = None, edges: list[dict] | None = None) -> dict:
    return {
        "agents": agents or [_agent("scout"), _agent("judge")],
        "edges": edges if edges is not None else [{"from": "scout", "to": "judge"}],
    }


def _create(client: TestClient, *, name: str = "morning desk", headers: dict = OWNER):
    return client.post(
        "/teams",
        json={"name": name, "description": "two roles", "definition": _definition()},
        headers=headers,
    )


def test_a_team_is_created_with_revision_one(client: TestClient) -> None:
    response = _create(client)

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "morning desk"
    assert body["latest_revision"] == 1
    # The catalogue entry carries no definition — see specs/teams-catalogue.
    assert "definition" not in body


def test_the_catalogue_lists_what_the_operator_saved(client: TestClient) -> None:
    _create(client, name="morning desk")
    _create(client, name="evening desk")

    listed = client.get("/teams", headers=OWNER).json()

    assert {row["name"] for row in listed} == {"morning desk", "evening desk"}
    assert all(row["latest_revision"] == 1 for row in listed)


def test_saving_a_revision_appends_and_the_earlier_one_still_reads(client: TestClient) -> None:
    team_id = _create(client).json()["id"]
    changed = _definition(agents=[_agent("scout"), _agent("judge") | {"prompt": "weigh it"}])

    saved = client.post(f"/teams/{team_id}/revisions", json={"definition": changed}, headers=OWNER)

    assert saved.status_code == 201
    assert saved.json()["version"] == 2
    first = client.get(f"/teams/{team_id}/revisions/1", headers=OWNER).json()
    assert first["definition"]["agents"][1]["prompt"] == "say something"
    latest = client.get(f"/teams/{team_id}/revisions/latest", headers=OWNER).json()
    assert latest["version"] == 2
    assert client.get(f"/teams/{team_id}", headers=OWNER).json()["latest_revision"] == 2


def test_an_edge_survives_the_round_trip_under_its_wire_name(client: TestClient) -> None:
    team_id = _create(client).json()["id"]

    revision = client.get(f"/teams/{team_id}/revisions/latest", headers=OWNER).json()

    assert revision["definition"]["edges"] == [{"from": "scout", "to": "judge"}]


def test_a_revision_reads_by_the_id_a_run_names_it_by(client: TestClient) -> None:
    # What a run watcher has in hand is `team_revision_id` and nothing else — reading the
    # team's latest instead would draw a graph the run is not running.
    team_id = _create(client).json()["id"]
    first = client.get(f"/teams/{team_id}/revisions/1", headers=OWNER).json()
    client.post(f"/teams/{team_id}/revisions", json={"definition": _definition()}, headers=OWNER)

    by_id = client.get(f"/revisions/{first['id']}", headers=OWNER)

    assert by_id.status_code == 200
    assert by_id.json() == first
    # Still the older one, after a newer revision landed on the same team.
    assert by_id.json()["version"] == 1


def test_someone_elses_revision_by_id_answers_like_a_missing_one(client: TestClient) -> None:
    revision_id = client.get(
        f"/teams/{_create(client).json()['id']}/revisions/1", headers=OWNER
    ).json()["id"]

    foreign = client.get(f"/revisions/{revision_id}", headers=STRANGER)
    absent = client.get(f"/revisions/{revision_id + 1000}", headers=STRANGER)

    assert foreign.status_code == absent.status_code == 404
    assert foreign.json() == absent.json()


def test_a_retired_team_leaves_the_catalogue_but_keeps_its_revisions(client: TestClient) -> None:
    team_id = _create(client).json()["id"]

    assert client.delete(f"/teams/{team_id}", headers=OWNER).status_code == 204

    assert client.get("/teams", headers=OWNER).json() == []
    assert client.get(f"/teams/{team_id}", headers=OWNER).status_code == 404
    kept = client.get(f"/teams/{team_id}/revisions/1", headers=OWNER)
    assert kept.status_code == 200
    assert kept.json()["version"] == 1


def test_someone_elses_team_answers_exactly_like_a_missing_one(client: TestClient) -> None:
    # specs/teams-browser-access, "odpowiedź jest nieodróżnialna od odpowiedzi o zespole
    # nieistniejącym" — same status, same body, for every route that names a team.
    team_id = _create(client).json()["id"]
    missing_id = team_id + 1000

    for path in ("/teams/{}", "/teams/{}/revisions/1", "/teams/{}/revisions/latest"):
        foreign = client.get(path.format(team_id), headers=STRANGER)
        absent = client.get(path.format(missing_id), headers=STRANGER)
        assert foreign.status_code == absent.status_code == 404
        assert foreign.json() == absent.json()

    assert client.get("/teams", headers=STRANGER).json() == []
    assert client.delete(f"/teams/{team_id}", headers=STRANGER).status_code == 404
    appended = client.post(
        f"/teams/{team_id}/revisions", json={"definition": _definition()}, headers=STRANGER
    )
    assert appended.status_code == 404
    # And nothing of the owner's moved while the stranger was refused.
    assert client.get(f"/teams/{team_id}", headers=OWNER).json()["latest_revision"] == 1


def test_a_dependency_cycle_is_refused_naming_the_agents_on_it(client: TestClient) -> None:
    body = {
        "name": "loop",
        "description": "",
        "definition": _definition(
            edges=[{"from": "scout", "to": "judge"}, {"from": "judge", "to": "scout"}]
        ),
    }

    response = client.post("/teams", json=body, headers=OWNER)

    assert response.status_code == 422
    assert "scout" in response.text and "judge" in response.text


def test_an_agent_wired_to_nothing_is_refused_naming_it(client: TestClient) -> None:
    body = {
        "name": "stray",
        "description": "",
        "definition": _definition(
            agents=[_agent("scout"), _agent("judge"), _agent("stray")],
            edges=[{"from": "scout", "to": "judge"}],
        ),
    }

    response = client.post("/teams", json=body, headers=OWNER)

    assert response.status_code == 422
    assert "stray" in response.text


def test_a_model_outside_the_catalogue_is_refused_naming_the_agent(client: TestClient) -> None:
    body = {
        "name": "wrong model",
        "description": "",
        "definition": _definition(
            agents=[_agent("scout"), _agent("judge", model_id="gpt-9-imaginary")]
        ),
    }

    response = client.post("/teams", json=body, headers=OWNER)

    assert response.status_code == 422
    assert "judge" in response.text and "gpt-9-imaginary" in response.text


def test_a_tool_no_server_announces_is_refused_naming_the_agent(client: TestClient) -> None:
    # No tool server is configured in these tests, so there is no session to ask. The module still serves
    # the catalogue and refuses only the definition that would need one.
    body = {
        "name": "tooled",
        "description": "",
        "definition": _definition(
            agents=[_agent("scout", tools=["get_candles"]), _agent("judge")]
        ),
    }

    response = client.post("/teams", json=body, headers=OWNER)

    assert response.status_code == 422
    assert "scout" in response.text and "get_candles" in response.text
    assert client.get("/teams", headers=OWNER).json() == []


def test_the_refusal_writes_nothing(client: TestClient) -> None:
    team_id = _create(client).json()["id"]

    refused = client.post(
        f"/teams/{team_id}/revisions",
        json={
            "definition": _definition(
                agents=[_agent("scout", model_id="gpt-9-imaginary")], edges=[]
            )
        },
        headers=OWNER,
    )

    assert refused.status_code == 422
    assert client.get(f"/teams/{team_id}", headers=OWNER).json()["latest_revision"] == 1


def test_a_team_with_nothing_arranged_answers_with_an_empty_layout(client: TestClient) -> None:
    # Never having been arranged is the ordinary state of a team, not a 404 — the canvas then places every
    # agent from its dependencies.
    team_id = _create(client).json()["id"]

    response = client.get(f"/teams/{team_id}/layout", headers=OWNER)

    assert response.status_code == 200
    assert response.json() == {"places": []}


def test_where_the_operator_left_an_agent_is_where_it_reads_back(client: TestClient) -> None:
    team_id = _create(client).json()["id"]
    places = [
        {"agent_key": "scout", "x": -120.5, "y": 40},
        {"agent_key": "judge", "x": 320, "y": 40},
    ]

    saved = client.put(f"/teams/{team_id}/layout", json={"places": places}, headers=OWNER)

    assert saved.status_code == 200
    assert client.get(f"/teams/{team_id}/layout", headers=OWNER).json() == {
        "places": [
            {"agent_key": "judge", "x": 320.0, "y": 40.0},
            {"agent_key": "scout", "x": -120.5, "y": 40.0},
        ]
    }


def test_moving_an_agent_is_not_a_new_revision(client: TestClient) -> None:
    """specs/terminal-teams, "Przesunięcie nie jest zmianą definicji" — the whole reason
    the layout lives in its own table rather than in the definition's JSONB."""
    team_id = _create(client).json()["id"]
    before = client.get(f"/teams/{team_id}/revisions/latest", headers=OWNER).json()

    client.put(
        f"/teams/{team_id}/layout",
        json={"places": [{"agent_key": "scout", "x": 10, "y": 10}]},
        headers=OWNER,
    )

    assert client.get(f"/teams/{team_id}", headers=OWNER).json()["latest_revision"] == 1
    assert client.get(f"/teams/{team_id}/revisions/latest", headers=OWNER).json() == before


def test_saving_a_layout_replaces_the_one_before_it(client: TestClient) -> None:
    # An agent removed from the team has to lose its place too, or a key reused later
    # inherits a position nobody chose for it.
    team_id = _create(client).json()["id"]
    client.put(
        f"/teams/{team_id}/layout",
        json={
            "places": [
                {"agent_key": "scout", "x": 0, "y": 0},
                {"agent_key": "judge", "x": 200, "y": 0},
            ]
        },
        headers=OWNER,
    )

    client.put(
        f"/teams/{team_id}/layout",
        json={"places": [{"agent_key": "scout", "x": 5, "y": 5}]},
        headers=OWNER,
    )

    assert client.get(f"/teams/{team_id}/layout", headers=OWNER).json() == {
        "places": [{"agent_key": "scout", "x": 5.0, "y": 5.0}]
    }


def test_the_same_agent_placed_twice_is_refused(client: TestClient) -> None:
    team_id = _create(client).json()["id"]

    response = client.put(
        f"/teams/{team_id}/layout",
        json={
            "places": [
                {"agent_key": "scout", "x": 0, "y": 0},
                {"agent_key": "scout", "x": 9, "y": 9},
            ]
        },
        headers=OWNER,
    )

    assert response.status_code == 422


def test_a_stranger_neither_reads_nor_moves_a_layout(client: TestClient) -> None:
    team_id = _create(client).json()["id"]
    client.put(
        f"/teams/{team_id}/layout",
        json={"places": [{"agent_key": "scout", "x": 1, "y": 2}]},
        headers=OWNER,
    )

    assert client.get(f"/teams/{team_id}/layout", headers=STRANGER).status_code == 404
    moved = client.put(
        f"/teams/{team_id}/layout",
        json={"places": [{"agent_key": "scout", "x": 99, "y": 99}]},
        headers=STRANGER,
    )

    assert moved.status_code == 404
    assert client.get(f"/teams/{team_id}/layout", headers=OWNER).json() == {
        "places": [{"agent_key": "scout", "x": 1.0, "y": 2.0}]
    }
