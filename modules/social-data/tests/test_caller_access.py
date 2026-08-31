"""Who may reach which surface. Nothing here writes, so the failure this record prevents is quieter:
Easy Auth admits an application to the process, and without the record the workbench would be past
every REST route the operator's screens were the audience for."""

from __future__ import annotations

import base64
import json

import httpx
import pytest

from social_data.caller_access import OPEN_PATHS, REST_PATHS, Surface, surface_for

WORKBENCH = "11111111-1111-1111-1111-111111111111"
TERMINAL = "22222222-2222-2222-2222-222222222222"
STRANGER = "33333333-3333-3333-3333-333333333333"


def principal_header(application: str) -> dict[str, str]:
    blob = {"claims": [{"typ": "azp", "val": application}]}
    return {"x-ms-client-principal": base64.b64encode(json.dumps(blob).encode()).decode()}


def person_header(object_id: str) -> dict[str, str]:
    """What Easy Auth sends about the signed-in *person*. Never what a surface is decided on."""
    return {"x-ms-client-principal-id": object_id}


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


@pytest.fixture
async def unconfigured(app, pool, settings):
    """A fresh deployment: the requirement is on and the record is empty, which is every caller
    refused rather than every caller admitted."""
    app.state.pool = pool
    app.state.settings = settings.model_copy(
        update={"require_authenticated_principal": True}
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://tests") as client:
        yield client


def test_every_published_rest_path_is_in_the_record(app) -> None:
    """A record derived from the application could never disagree with it, and disagreeing is the
    whole job: a new route stays unreachable until somebody decides which surface it belongs to."""
    published = set(app.openapi()["paths"])
    recorded = set(REST_PATHS) | OPEN_PATHS

    assert published <= recorded, (
        f"these routes are published and unrecorded: {sorted(published - recorded)}"
    )


def test_a_path_nobody_recorded_belongs_to_no_surface() -> None:
    assert surface_for("/something-new") is None


def test_the_open_paths_are_exactly_two_and_carry_no_data() -> None:
    """Both are excluded from Easy Auth in production, so any addition here is a route reachable
    with no identity at all. Equality rather than membership, so it fails."""
    assert OPEN_PATHS == {"/", "/ping"}


def test_the_tool_mount_and_its_trailing_slash_are_the_same_surface() -> None:
    assert surface_for("/mcp") is Surface.TOOLS
    assert surface_for("/mcp/") is Surface.TOOLS


@pytest.mark.db
async def test_a_request_with_no_identity_is_refused(guarded) -> None:
    assert (await guarded.get("/posts")).status_code == 401


@pytest.mark.db
async def test_a_stranger_is_refused_on_both_surfaces(guarded) -> None:
    headers = principal_header(STRANGER)

    assert (await guarded.get("/posts", headers=headers)).status_code == 403
    assert (await guarded.get("/mcp/", headers=headers)).status_code == 403


@pytest.mark.db
async def test_the_tool_caller_does_not_reach_the_contract(guarded) -> None:
    answer = await guarded.get("/posts", headers=principal_header(WORKBENCH))

    assert answer.status_code == 403


@pytest.mark.db
async def test_the_screens_reach_the_contract(guarded) -> None:
    answer = await guarded.get("/posts", headers=principal_header(TERMINAL))

    assert answer.status_code == 200


@pytest.mark.db
async def test_the_person_signed_in_never_stands_in_for_the_application(guarded) -> None:
    """Measured on 19 August 2026 in another module by deploying the opposite assumption: the
    principal header names a person, and reading it as an application refuses every real caller."""
    answer = await guarded.get("/posts", headers=person_header(TERMINAL))

    assert answer.status_code == 401


@pytest.mark.db
async def test_an_empty_record_refuses_everyone(unconfigured) -> None:
    assert (await unconfigured.get("/posts", headers=principal_header(TERMINAL))).status_code == 403
    assert (await unconfigured.get("/mcp/", headers=principal_header(WORKBENCH))).status_code == 403


@pytest.mark.db
async def test_the_probe_reaches_health_and_the_name_without_an_identity(guarded) -> None:
    named = await guarded.get("/")

    assert named.status_code == 200
    assert named.json()["service"] == "social-data"
    assert (await guarded.get("/ping")).status_code == 200
