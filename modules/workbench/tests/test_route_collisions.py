"""The three paths both surfaces published, and where they went. The second test asserts behaviour, because a path
parameter compiles to a matcher that runs before FastAPI reads it as an `int`: reversing two lines answers 422."""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

import agent.surface
import teams.surface
import teams_tools
from teams.routers import catalogue, memory, models, runs, schedules, tools, usage


class _Catalogue:
    """Enough of a catalogue for the route to answer: `GET /models` reads `entries()` and
    nothing else."""

    def entries(self):
        return []


@pytest.fixture
def surfaces() -> TestClient:
    """Both surfaces on one application, assembled the way `workbench/app.py` assembles them — and with no
    lifespan, so this says nothing about a database. State is stubbed rather than built."""
    app = FastAPI()
    agent.surface.include(app)
    teams.surface.include(app)
    stub = SimpleNamespace(
        catalogue=_Catalogue(),
        settings=SimpleNamespace(require_authenticated_principal=False),
    )
    app.state.agent = stub
    app.state.teams = stub
    return TestClient(app, raise_server_exceptions=False)


def test_each_surface_answers_its_own_catalogue(surfaces: TestClient) -> None:
    assert surfaces.get("/models").status_code == 200
    assert surfaces.get("/teams/models").status_code == 200


def test_the_literal_beats_the_team_id_it_looks_like(surfaces: TestClient) -> None:
    """The failure this guards is specific: `422` with `int_parsing` on `team_id`, which is
    what `/teams/{team_id}` answers when it takes the request first."""
    response = surfaces.get("/teams/models")
    assert response.status_code == 200, response.text
    assert "int_parsing" not in response.text


def test_a_real_team_id_still_reaches_the_catalogue_route(surfaces: TestClient) -> None:
    """The other half: putting the literals first must not shadow the parameterised route. It answers by failing on its
    own state rather than on routing, which is enough — a `404` from the router would mean it was never reached."""
    assert surfaces.get("/teams/7").status_code != 404


def test_nothing_else_moved(surfaces: TestClient) -> None:
    """A sample from each surface, at the path it had before the merge. The point is not coverage of every route —
    `contract:check` is that — but that the prefix applied to two routers and not to a whole surface."""
    for path in ("/sessions", "/prompt", "/chart", "/drawings", "/usage", "/teams", "/tools"):
        assert surfaces.get(path).status_code != 404, path


_TOOL_CALL = re.compile(r'_call\(teams, context, "([A-Z]+)", f?"([^"]+)"')


def _team_tool_calls() -> set[tuple[str, str]]:
    """Every request the team tools make, read off their source with each `{…}` filled in: they reach the assembled app
    by path, so a path that moved lands on the other surface's route and answers its numbers instead."""
    calls = set()
    for source in (Path(teams_tools.__file__).parent / "tools").glob("*.py"):
        for method, path in _TOOL_CALL.findall(source.read_text(encoding="utf-8")):
            calls.add((method, re.sub(r"\{[^}]*\}", "1", path.replace("{action}", "enable"))))
    return calls


def test_every_path_the_team_tools_call_is_a_teams_route(surfaces: TestClient) -> None:
    """`/usage` and `/models` answered the conversation's whole bill and catalogue for a run's cost and a team's models.
    The router writes the endpoint it chose into the scope; the request itself may fail on the stubbed state."""
    calls = _team_tool_calls()
    assert ("GET", "/teams/usage") in calls
    app = surfaces.app
    teams_endpoints = {
        route.endpoint
        for module in (catalogue, memory, models, runs, schedules, tools, usage)
        for route in module.router.routes
        if isinstance(route, APIRoute)
    }
    answered: dict[str, object] = {}

    async def recording(scope, receive, send):
        try:
            await app(scope, receive, send)
        finally:
            answered[scope["path"]] = scope.get("endpoint")

    client = TestClient(recording, raise_server_exceptions=False)
    for method, path in sorted(calls):
        client.request(method, path)
        assert answered[path] in teams_endpoints, (method, path, answered[path])
