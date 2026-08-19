"""`GET /models`, and what happens to a revision whose model is later withdrawn.

Through the real lifespan like the other route tests: the catalogue the routes read is
the one `Settings()` built, so a test assembling its own would prove nothing about the
module that gets deployed.
"""

from __future__ import annotations

from collections.abc import Iterator

import asyncpg
import pytest
from fastapi.testclient import TestClient

from teams import store
from teams.app import app
from teams.contract import TeamDefinition, TeamRevisionOut
from teams.models_catalogue import ModelCatalogue
from teams.validation import DefinitionRefused, check_runnable

pytestmark = pytest.mark.db

CHEAP = "gpt-5.6-mini"
DEAR = "gpt-5.6-luna"

# Two entries, and the dearer one first in the list — `cost_rank`, not list order, is
# what the published catalogue is sorted by (specs/teams-models).
_MODELS = (
    "["
    f'{{"id":"{DEAR}","model":"luna-prod","display_name":"Luna","cost_rank":2,'
    '"input_rate_per_1m":"1.25","output_rate_per_1m":"10"},'
    f'{{"id":"{CHEAP}","model":"mini-prod","display_name":"Mini","cost_rank":1,'
    '"input_rate_per_1m":"0.1","output_rate_per_1m":"0.4"}'
    "]"
)

OWNER = {"X-MS-CLIENT-PRINCIPAL-ID": "operator-1"}


@pytest.fixture(autouse=True)
def _env(migrated_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", migrated_url)
    monkeypatch.setenv("OPENAI_API_KEY", "key")
    monkeypatch.setenv("MODELS", _MODELS)


@pytest.fixture
def client(db: asyncpg.Connection) -> Iterator[TestClient]:
    with TestClient(app) as started:
        yield started


def _agent(key: str, *, model_id: str = DEAR) -> dict:
    return {"key": key, "role": f"the {key}", "prompt": "say something", "model_id": model_id}


def _create(client: TestClient, agents: list[dict]) -> int:
    response = client.post(
        "/teams",
        json={
            "name": "mixed desk",
            "description": "",
            "definition": {"agents": agents, "edges": []},
        },
        headers=OWNER,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_the_catalogue_is_published_cheapest_first_with_its_rates(client: TestClient) -> None:
    published = client.get("/models").json()

    assert published == [
        {
            "id": CHEAP,
            "display_name": "Mini",
            "cost_rank": 1,
            "input_rate_per_1m": "0.1",
            "output_rate_per_1m": "0.4",
        },
        {
            "id": DEAR,
            "display_name": "Luna",
            "cost_rank": 2,
            "input_rate_per_1m": "1.25",
            "output_rate_per_1m": "10",
        },
    ]


def test_two_agents_in_one_team_may_carry_different_models(client: TestClient) -> None:
    # specs/teams-models, "Model wybiera się osobno dla każdego agenta" — the whole point
    # of the module being able to measure where the dearer model changes anything.
    team_id = _create(client, [_agent("scout", model_id=CHEAP), _agent("judge", model_id=DEAR)])

    revision = client.get(f"/teams/{team_id}/revisions/latest", headers=OWNER).json()

    assert [agent["model_id"] for agent in revision["definition"]["agents"]] == [CHEAP, DEAR]


def test_an_agent_with_no_model_is_refused_naming_that_agent(client: TestClient) -> None:
    body = {
        "name": "modelless",
        "description": "",
        "definition": {
            "agents": [_agent("scout"), {"key": "judge", "role": "judge", "prompt": "weigh it"}],
            "edges": [],
        },
    }

    response = client.post("/teams", json=body, headers=OWNER)

    assert response.status_code == 422
    # By its key, not by its position in the list — an operator reading `agents.1` is
    # counting rows on a canvas to find out which role is meant.
    assert "judge" in response.text


def test_a_withdrawn_model_leaves_the_catalogue_and_its_revisions_readable(
    client: TestClient,
) -> None:
    # specs/teams-models, "Model wycofany z konfiguracji MUST zniknąć z katalogu, a
    # rewizje wskazujące go MUST pozostać czytelne wraz ze śladem przebiegów".
    team_id = _create(client, [_agent("scout", model_id=DEAR)])
    revision = client.get(f"/teams/{team_id}/revisions/latest", headers=OWNER).json()

    # The operator drops the dear model from the configuration and restarts — the state a
    # narrower catalogue on the running app stands in for.
    settings = app.state.settings
    app.state.catalogue = ModelCatalogue([e for e in settings.models if e.id == CHEAP])

    assert [entry["id"] for entry in client.get("/models").json()] == [CHEAP]
    # Still readable, unchanged, and so is the catalogue entry pointing at it.
    reread = client.get(f"/teams/{team_id}/revisions/{revision['version']}", headers=OWNER)
    assert reread.status_code == 200
    assert reread.json() == revision
    assert client.get(f"/teams/{team_id}", headers=OWNER).status_code == 200

    # Saving a *new* revision on the withdrawn model is refused, naming agent and model.
    refused = client.post(
        f"/teams/{team_id}/revisions",
        json={"definition": {"agents": [_agent("scout", model_id=DEAR)], "edges": []}},
        headers=OWNER,
    )
    assert refused.status_code == 422
    assert "scout" in refused.text and DEAR in refused.text


async def test_a_revision_on_a_withdrawn_model_keeps_its_runs(db: asyncpg.Connection) -> None:
    # The other half of the same requirement, below HTTP because a run has no route until
    # group 7: what the model catalogue does is refuse the *next* run, and it touches
    # neither the revision nor the trace of the runs already there.
    definition = TeamDefinition.model_validate(
        {"agents": [_agent("scout", model_id=DEAR)], "edges": []}
    )
    team, revision = await store.create_team(
        db, owner_principal="operator-1", name="desk", description="", definition=definition
    )
    run_id = await db.fetchval(
        "INSERT INTO runs (team_revision_id, owner_principal, status, finished_at) "
        "VALUES ($1, 'operator-1', 'completed', now()) RETURNING id",
        revision["id"],
    )

    check_runnable(definition, model_ids={DEAR, CHEAP})  # while the model is configured
    with pytest.raises(DefinitionRefused) as err:
        check_runnable(definition, model_ids={CHEAP})
    assert "scout" in str(err.value) and DEAR in str(err.value)

    kept = await store.get_revision(
        db, team_id=team["id"], owner_principal="operator-1", version=1
    )
    assert kept is not None
    assert TeamRevisionOut.from_row(dict(kept)).definition == definition
    assert await db.fetchval("SELECT count(*) FROM runs WHERE id = $1", run_id) == 1
