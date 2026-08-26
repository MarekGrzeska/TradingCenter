"""The three paths both surfaces published, and where they went. `/health` was identical and is one route;
the two that answered different shapes moved under `/teams/`.

The second test asserts behaviour rather than a list: a path parameter compiles to a segment matcher that
runs before FastAPI reads it as an `int`, so the literal wins only by being registered first — measured on
FastAPI 0.141.1, where reversing the two lines answers `422` instead of the catalogue."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import agent.surface
import teams.surface


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
    """The other half: putting the literals first must not shadow the parameterised route.
    It answers here by failing on its own state rather than on routing, which is enough —
    a `404` from the router would mean the route was never reached."""
    assert surfaces.get("/teams/7").status_code != 404


def test_nothing_else_moved(surfaces: TestClient) -> None:
    """A sample from each surface, at the path it had before the merge. The point is not
    coverage of every route — `contract:check` in the terminal is that — but that the prefix
    applied to two routers and not to a whole surface."""
    for path in ("/sessions", "/prompt", "/chart", "/drawings", "/usage", "/teams", "/tools"):
        assert surfaces.get(path).status_code != 404, path
