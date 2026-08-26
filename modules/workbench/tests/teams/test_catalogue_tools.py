"""Saving a definition that assigns tools, with a tool server actually answering — the other half of
`test_catalogue_routes.py`, and the check the save-time rule was written for: the names are confirmed
against what the server announces right now, not against a list this module keeps."""

from __future__ import annotations

from collections.abc import Iterator

import asyncpg
import pytest
from fastapi.testclient import TestClient

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


@pytest.fixture
def client(
    workbench_env: None,
    db: asyncpg.Connection,
    migrated_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    """The app against a stand-in tool server announcing three tools. `db` is depended on
    for its truncation — every test here starts against an empty catalogue."""
    with serving_sync() as url:
        monkeypatch.setenv("MARKET_MCP_URL", url)
        for key, value in _ENV.items():
            monkeypatch.setenv(key, value)
        with TestClient(app) as started:
            yield started


def _body(tools: list[str]) -> dict:
    return {
        "name": "with tools",
        "description": "",
        "definition": {
            "agents": [
                {
                    "key": "reader",
                    "role": "the reader",
                    "prompt": "read the market",
                    "model_id": MODEL_ID,
                    "tools": tools,
                }
            ],
            "edges": [],
        },
    }


def test_a_definition_naming_announced_tools_is_saved(client: TestClient) -> None:
    response = client.post(
        "/teams", json=_body(["get_last_price", "read_indicators"]), headers=OWNER
    )

    assert response.status_code == 201, response.text
    team_id = response.json()["id"]
    saved = client.get(f"/teams/{team_id}/revisions/latest", headers=OWNER)
    assert saved.json()["definition"]["agents"][0]["tools"] == [
        "get_last_price",
        "read_indicators",
    ]


def test_a_definition_naming_a_tool_the_server_does_not_announce_is_refused(
    client: TestClient,
) -> None:
    response = client.post("/teams", json=_body(["invent_a_price"]), headers=OWNER)

    assert response.status_code == 422
    # The agent and the tool, both — the operator's next move is that agent's panel.
    assert "reader" in response.text
    assert "invent_a_price" in response.text


def test_the_names_come_from_the_server_not_from_this_module(client: TestClient) -> None:
    """The assertion that fails the day someone writes a local list of tool names: the stand-in publishes
    exactly three, and a fourth market-mcp really has is refused because *this* server does not announce it."""
    response = client.post("/teams", json=_body(["get_candles"]), headers=OWNER)

    assert response.status_code == 422
