"""`GET /tools` — the three answers, and why the last two are not the same one.

The route exists so the terminal's picker can be built from what the server announces and
from nothing else (`terminal-teams`). What it has to get right is the difference between
a module that announces nothing and a module that could not ask: the first is a working
configuration, the second is an outage, and a terminal told `[]` for both would show the
operator an empty picker while the tools are sitting there.
"""

from __future__ import annotations

from collections.abc import Iterator

import asyncpg
import pytest
from fastapi.testclient import TestClient

from teams.app import app

from .mcp_stand_in import free_port, serving_sync

pytestmark = pytest.mark.db

_ENV = {
    "OPENAI_API_KEY": "key",
    "MODELS": (
        '[{"id":"gpt-5.6-luna","model":"luna-prod","display_name":"Luna",'
        '"cost_rank":1,"input_rate_per_1m":"1","output_rate_per_1m":"6"}]'
    ),
}


@pytest.fixture
def _env(db: asyncpg.Connection, migrated_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", migrated_url)
    monkeypatch.delenv("MARKET_MCP_URL", raising=False)
    for key, value in _ENV.items():
        monkeypatch.setenv(key, value)


@pytest.fixture
def announcing(_env: None, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    with serving_sync(("get_last_price", "read_indicators")) as url:
        monkeypatch.setenv("MARKET_MCP_URL", url)
        with TestClient(app) as started:
            yield started


def test_what_the_server_announces_is_what_the_route_publishes(announcing: TestClient) -> None:
    published = announcing.get("/tools").json()

    assert [tool["name"] for tool in published] == ["get_last_price", "read_indicators"]
    # The description travels too — it is the only thing beside the name the picker can
    # show, and this module writes neither.
    assert published[0]["description"].startswith("Returns the last price")
    # And nothing else: an input schema here would be a copy of somebody else's contract.
    assert set(published[0]) == {"name", "description"}


def test_no_tool_server_configured_announces_nothing_rather_than_failing(
    _env: None,
) -> None:
    # specs/teams-tool-access, "Moduł startuje bez skonfigurowanego serwera narzędzi" —
    # a working configuration, so the route answers with the empty catalogue it is.
    with TestClient(app) as client:
        response = client.get("/tools")

    assert response.status_code == 200
    assert response.json() == []


def test_a_configured_server_that_cannot_be_asked_is_an_outage_not_an_empty_list(
    _env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MARKET_MCP_URL", f"http://127.0.0.1:{free_port()}")

    with TestClient(app) as client:
        response = client.get("/tools")

    assert response.status_code == 503
    # The message names the server, because the operator's next move is at that end.
    assert "127.0.0.1" in response.json()["detail"]


def test_the_route_does_not_need_the_run_session_and_leaves_it_alone(
    announcing: TestClient,
) -> None:
    """Two reads in a row, each through a session of its own (`announced_tools`).

    The one thing this asserts is that the second answers at all: a session opened inside
    a request's task and left open corrupts anyio's scope stack, and the failure shows up
    on the way out of some later request rather than here (`tools/client.py`).
    """
    assert announcing.get("/tools").status_code == 200
    assert announcing.get("/tools").status_code == 200
    assert app.state.tools._session is None  # the long-lived one was never opened
