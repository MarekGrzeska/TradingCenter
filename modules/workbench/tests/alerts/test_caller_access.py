"""Who may reach which surface. Easy Auth admits an application to the process, and without the record the workbench
would be past every REST route the operator's screen was the audience for."""

from __future__ import annotations

import base64
import json

import httpx
import pytest

from alerts.caller_access import OPEN_PATHS, REST_PATHS, Surface, surface_for

WORKBENCH = "11111111-1111-1111-1111-111111111111"
TERMINAL = "22222222-2222-2222-2222-222222222222"
STRANGER = "33333333-3333-3333-3333-333333333333"


def principal_header(application: str) -> dict[str, str]:
    blob = {"claims": [{"typ": "azp", "val": application}]}
    return {"x-ms-client-principal": base64.b64encode(json.dumps(blob).encode()).decode()}


@pytest.fixture
async def guarded(app, pool, settings):
    """The application with the requirement on, as production runs it."""
    app.state.pool = pool
    app.state.settings = settings.model_copy(
        update={
            "require_authenticated_principal": True,
            "tool_caller_application_ids": WORKBENCH,
            "rest_caller_application_ids": TERMINAL,
        }
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://tests") as client:
        yield client


def test_every_published_rest_path_is_in_the_record(app) -> None:
    """A record derived from the application could never disagree with it, and disagreeing is the whole job: a new route
    stays unreachable until somebody decides which surface it belongs to."""
    published = set(app.openapi()["paths"])

    assert published <= set(REST_PATHS) | OPEN_PATHS, (
        f"published and unrecorded: {sorted(published - set(REST_PATHS) - OPEN_PATHS)}"
    )


def test_the_open_paths_are_exactly_two_and_carry_no_data() -> None:
    """Both are excluded from Easy Auth in production, so an addition is a route reachable with no identity at all."""
    assert OPEN_PATHS == {"/", "/ping"}


def test_a_path_nobody_recorded_belongs_to_no_surface() -> None:
    assert surface_for("/something-new") is None
    assert surface_for("/mcp") is Surface.TOOLS


@pytest.mark.db
async def test_the_screen_reaches_the_contract_and_the_tool_caller_does_not(guarded) -> None:
    assert (await guarded.get("/health", headers=principal_header(TERMINAL))).status_code == 200
    assert (await guarded.get("/health", headers=principal_header(WORKBENCH))).status_code == 403


@pytest.mark.db
async def test_no_identity_and_a_stranger_are_refused(guarded) -> None:
    assert (await guarded.get("/health")).status_code == 401
    assert (await guarded.get("/health", headers=principal_header(STRANGER))).status_code == 403


@pytest.mark.db
async def test_the_probe_reaches_the_name_without_an_identity(guarded) -> None:
    named = await guarded.get("/")

    assert named.status_code == 200
    assert named.json()["service"] == "alerts"
