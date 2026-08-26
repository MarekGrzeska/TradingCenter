"""Which caller may reach which surface, and the default that makes the record worth having: the record is
held against the published document, so an undecided route fails CI rather than becoming reachable."""

from __future__ import annotations

import base64
import json

import httpx
import pytest

from strategy.app import create_app
from strategy.caller_access import OPEN_PATHS, REST_PATHS, Surface, surface_for
from strategy.config import Settings

# Published by FastAPI itself rather than by a router, so they never appear in the document
# — but they do describe the REST contract, which is why the record names them.
FRAMEWORK_PATHS = frozenset({"/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"})


def principal(application: str) -> dict[str, str]:
    """What Easy Auth puts on a request it let through, as this module reads it."""
    blob = {"claims": [{"typ": "azp", "val": application}]}
    encoded = base64.b64encode(json.dumps(blob).encode()).decode()
    return {"x-ms-client-principal": encoded}


@pytest.fixture
def guarded_app():
    """An application configured the way a deployed one is: identity required, two lists."""
    app = create_app()
    app.state.settings = Settings(
        database_url="postgresql://localhost:5432/test?sslmode=require",
        database_user="test-user",
        require_authenticated_principal=True,
        tool_caller_application_ids="workbench-app-id",
        rest_caller_application_ids="terminal-app-id",
        _env_file=None,
    )
    return app


@pytest.fixture
async def guarded(guarded_app):
    transport = httpx.ASGITransport(app=guarded_app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://strategy.test") as client:
        yield client


class TestTheRecord:
    def test_a_path_nobody_recorded_belongs_to_no_surface(self) -> None:
        """The default matters more than any single entry."""
        assert surface_for("/something-new") is None

    def test_the_tool_mount_and_everything_under_it_is_the_tool_surface(self) -> None:
        assert surface_for("/mcp") is Surface.TOOLS
        assert surface_for("/mcp/") is Surface.TOOLS
        assert surface_for("/mcp/messages") is Surface.TOOLS

    def test_a_trailing_slash_is_the_same_route(self) -> None:
        assert surface_for("/watches/") is Surface.REST

    def test_the_open_paths_are_exactly_one(self) -> None:
        """Equality rather than membership, so **any** addition here fails CI — including
        one that carries data, which is the case this assertion exists for."""
        assert OPEN_PATHS == {"/ping"}

    def test_every_published_route_is_in_the_record(self, guarded_app) -> None:
        """Held against the document rather than derived from it: a record derived from the
        application could never disagree with it, and disagreeing is the whole job."""
        unrecorded = {
            path
            for path in _published(guarded_app)
            if path not in OPEN_PATHS and path not in REST_PATHS and not path.startswith("/mcp")
        }
        assert not unrecorded, (
            f"{sorted(unrecorded)} are published and belong to no surface. Add each to "
            "REST_PATHS or OPEN_PATHS — deliberately, having decided which caller it is for."
        )

    def test_the_record_names_no_route_that_is_gone(self, guarded_app) -> None:
        """The other direction, which keeps the list from becoming a graveyard — a record
        naming routes that do not exist grants nothing and hides what it does grant."""
        stale = {
            path
            for path in REST_PATHS
            if path not in _published(guarded_app) and path not in FRAMEWORK_PATHS
        }
        assert not stale, f"{sorted(stale)} are in the record and published by nothing"


class TestWhoGetsIn:
    async def test_the_open_path_needs_no_identity(self, guarded) -> None:
        assert (await guarded.get("/ping")).status_code == 200

    async def test_a_request_with_no_identity_is_refused(self, guarded) -> None:
        response = await guarded.get("/strategies")

        assert response.status_code == 401
        assert response.json() == {"detail": "not authenticated"}

    async def test_the_rest_caller_reaches_rest(self, guarded) -> None:
        # The root rather than `/strategies`, which the refusals below use: what is under test is the gate, and it is
        # the only thing this application has that can answer without a database behind it.
        response = await guarded.get("/", headers=principal("terminal-app-id"))

        assert response.status_code == 200

    async def test_the_tool_caller_does_not_reach_rest(self, guarded) -> None:
        """Easy Auth authorizes an application, not a route. This is the part it cannot
        say: the workbench is here for `pending_setups`, not for the operator's routes."""
        response = await guarded.get("/strategies", headers=principal("workbench-app-id"))

        assert response.status_code == 403
        assert "rest" in response.json()["detail"]

    async def test_the_rest_caller_does_not_reach_the_tools(self, guarded) -> None:
        response = await guarded.post("/mcp", headers=principal("terminal-app-id"))

        assert response.status_code == 403

    async def test_a_path_in_no_surface_is_refused_rather_than_passed(self, guarded) -> None:
        response = await guarded.get("/something-new", headers=principal("terminal-app-id"))

        assert response.status_code == 403

    async def test_a_principal_header_naming_a_person_is_not_an_application(
        self, guarded
    ) -> None:
        """Measured on market-data in production on 19 August 2026: for a delegated token the principal-id header
        carries the signed-in *person's* object id, so a record of application identifiers can never match it."""
        response = await guarded.get(
            "/strategies", headers={"x-ms-client-principal-id": "terminal-app-id"}
        )

        assert response.status_code == 401


class TestWithoutAPlatformInFront:
    async def test_local_work_needs_no_identity(self, api) -> None:
        """Nothing stands in front locally, so there is no identity to have and no list to
        be on. The `api` fixture's settings have the requirement off, as a `.env` does."""
        assert (await api.get("/strategies")).status_code == 200


def _published(app) -> set[str]:
    """Every path in the document this application publishes. Read off `app.openapi()` rather than walked
    out of the router: newer FastAPI wraps an included router, and walking it found four framework routes."""
    return set(app.openapi()["paths"])
