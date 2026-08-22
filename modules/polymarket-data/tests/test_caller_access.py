"""Who may reach which surface.

The record and its failure modes. A list with no test of its failure mode is a list nobody
knows works, and here the failure mode that matters is not the obvious one: the tool caller
*is* allowed to write — to the list of observations — so what the record has to keep it away
from is deleting collected history, which nothing can undo.
"""

from __future__ import annotations

import base64
import json

import httpx
import pytest

from polymarket_data.caller_access import OPEN_PATHS, REST_PATHS, Surface, surface_for

WORKBENCH = "11111111-1111-1111-1111-111111111111"
TERMINAL = "22222222-2222-2222-2222-222222222222"
STRANGER = "33333333-3333-3333-3333-333333333333"


def principal_header(application: str) -> dict[str, str]:
    blob = {"claims": [{"typ": "azp", "val": application}]}
    encoded = base64.b64encode(json.dumps(blob).encode()).decode()
    return {"x-ms-client-principal": encoded}


@pytest.fixture
async def guarded(app, pool, settings):
    """The application with the requirement on, as production runs it."""
    import fakes

    app.state.pool = pool
    app.state.settings = settings.model_copy(
        update={
            "require_authenticated_principal": True,
            "tool_caller_application_ids": WORKBENCH,
            "rest_caller_application_ids": TERMINAL,
        }
    )
    app.state.provider = fakes.FakeProvider()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://tests") as client:
        yield client


class TestTheRecordItself:
    def test_every_published_rest_path_is_in_the_record(self, app) -> None:
        """A route derived from the application could never disagree with it, and
        disagreeing is the whole job: a new route stays unreachable until somebody decides
        which surface it belongs to."""
        published = set(app.openapi()["paths"])
        recorded = set(REST_PATHS) | OPEN_PATHS
        assert published <= recorded, (
            f"these routes are published and unrecorded: {sorted(published - recorded)}"
        )

    def test_a_path_nobody_recorded_belongs_to_no_surface(self) -> None:
        assert surface_for("/something-new") is None

    def test_the_open_paths_are_exactly_two_and_carry_no_data(self) -> None:
        """Both are excluded from Easy Auth in production, so any addition here is a route
        reachable with no identity at all. Equality rather than membership, so it fails."""
        assert OPEN_PATHS == {"/", "/ping"}

    def test_the_tool_mount_and_its_trailing_slash_are_the_same_surface(self) -> None:
        assert surface_for("/mcp") is Surface.TOOLS
        assert surface_for("/mcp/") is Surface.TOOLS


@pytest.mark.db
class TestRefusals:
    async def test_a_request_with_no_identity_is_refused(self, guarded) -> None:
        assert (await guarded.get("/events")).status_code == 401

    async def test_the_tool_caller_cannot_delete_collected_history(self, guarded) -> None:
        """The pair that matters in this module. The tool caller writes by design — it
        starts and stops observations — so the boundary is not "may it write" but "may it
        reach the one act nobody can undo"."""
        response = await guarded.delete(
            "/events/e-1/history", headers=principal_header(WORKBENCH)
        )
        assert response.status_code == 403

    async def test_the_tool_caller_cannot_reach_the_rest_contract_at_all(
        self, guarded
    ) -> None:
        assert (
            await guarded.get("/events", headers=principal_header(WORKBENCH))
        ).status_code == 403

    async def test_the_rest_caller_cannot_reach_the_tool_surface(self, guarded) -> None:
        response = await guarded.post("/mcp/", headers=principal_header(TERMINAL))
        assert response.status_code == 403

    async def test_an_identity_the_record_does_not_name_is_refused(self, guarded) -> None:
        assert (
            await guarded.get("/events", headers=principal_header(STRANGER))
        ).status_code == 403

    async def test_a_path_outside_the_record_is_refused_rather_than_passed(
        self, guarded
    ) -> None:
        response = await guarded.get("/not-a-route", headers=principal_header(TERMINAL))
        assert response.status_code == 403
        assert "not open to any caller" in response.json()["detail"]

    async def test_an_empty_record_admits_nobody(self, app, pool, settings) -> None:
        """A fresh deployment has empty lists, and "the list was empty" must never be the
        reading under which everyone is allowed."""
        import fakes

        app.state.pool = pool
        app.state.settings = settings.model_copy(
            update={"require_authenticated_principal": True}
        )
        app.state.provider = fakes.FakeProvider()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://tests") as client:
            assert (
                await client.get("/events", headers=principal_header(TERMINAL))
            ).status_code == 403


@pytest.mark.db
class TestWhatStaysOpen:
    async def test_the_health_probe_needs_no_identity(self, guarded) -> None:
        """The platform restarts the container on this answer. It has no identity to
        present and does not speak MCP."""
        assert (await guarded.get("/ping")).status_code == 200

    async def test_the_deploy_probe_path_needs_no_identity(self, guarded) -> None:
        response = await guarded.get("/")
        assert response.status_code == 200
        assert response.json()["service"] == "polymarket-data"

    async def test_the_rest_caller_reaches_the_contract(self, guarded) -> None:
        assert (
            await guarded.get("/events", headers=principal_header(TERMINAL))
        ).status_code == 200
