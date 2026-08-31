"""Who may reach which surface. Both surfaces send, so what this record keeps apart is not reading
from writing: it is that creating a bot and binding a destination are REST alone — and Easy Auth
admits an application to the process, not to a route."""

from __future__ import annotations

import base64
import json

import httpx
import pytest
from fakes import FakeBotApi, RecordingWatcher

from telegram_gateway.caller_access import OPEN_PATHS, REST_PATHS, Surface, surface_for

WORKBENCH = "11111111-1111-1111-1111-111111111111"
OPERATOR_TOOLING = "22222222-2222-2222-2222-222222222222"
STRANGER = "33333333-3333-3333-3333-333333333333"


def principal_header(application: str) -> dict[str, str]:
    blob = {"claims": [{"typ": "azp", "val": application}]}
    return {"x-ms-client-principal": base64.b64encode(json.dumps(blob).encode()).decode()}


def person_header(object_id: str) -> dict[str, str]:
    """What Easy Auth sends about the signed-in *person*. Never what a surface is decided on."""
    return {"x-ms-client-principal-id": object_id}


def _wire(app, pool, settings, **overrides):
    app.state.pool = pool
    app.state.telegram = FakeBotApi()
    app.state.watcher = RecordingWatcher()
    app.state.settings = settings.model_copy(update=overrides)


@pytest.fixture
async def guarded(app, pool, settings):
    """The application with the requirement on, as production runs it."""
    _wire(
        app,
        pool,
        settings,
        require_authenticated_principal=True,
        tool_caller_application_ids=WORKBENCH,
        rest_caller_application_ids=OPERATOR_TOOLING,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://tests") as client:
        yield client


@pytest.fixture
async def unconfigured(app, pool, settings):
    """A fresh deployment: the requirement is on and the record is empty, which is every caller
    refused rather than every caller admitted."""
    _wire(app, pool, settings, require_authenticated_principal=True)
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
    """Task 8.3's rule, at the layer that holds it: the record is consulted before routing, so a
    route added and nothing else refuses an unknown caller by default rather than by remembering."""
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
    assert (await guarded.get("/destinations")).status_code == 401


@pytest.mark.db
async def test_a_stranger_is_refused_on_both_surfaces(guarded) -> None:
    headers = principal_header(STRANGER)

    assert (await guarded.get("/destinations", headers=headers)).status_code == 403
    assert (await guarded.get("/mcp/", headers=headers)).status_code == 403


@pytest.mark.db
async def test_the_tool_caller_does_not_reach_the_routes_that_manage_bots(guarded) -> None:
    """The whole reason the lists are disjoint. A model may send; a bot outlives the conversation."""
    headers = principal_header(WORKBENCH)

    assert (await guarded.get("/bots", headers=headers)).status_code == 403
    assert (
        await guarded.post("/destinations", json={"name": "o", "bot": "b"}, headers=headers)
    ).status_code == 403


@pytest.mark.db
async def test_the_rest_caller_does_not_reach_the_tool_surface(guarded) -> None:
    answer = await guarded.get("/mcp/", headers=principal_header(OPERATOR_TOOLING))

    assert answer.status_code == 403


@pytest.mark.db
async def test_the_recorded_rest_caller_reaches_the_contract(guarded) -> None:
    answer = await guarded.get("/destinations", headers=principal_header(OPERATOR_TOOLING))

    assert answer.status_code == 200


@pytest.mark.db
async def test_the_person_signed_in_never_stands_in_for_the_application(guarded) -> None:
    """Measured on 19 August 2026 in another module by deploying the opposite assumption: the
    principal header names a person, and reading it as an application refuses every real caller."""
    answer = await guarded.get("/destinations", headers=person_header(OPERATOR_TOOLING))

    assert answer.status_code == 401


@pytest.mark.db
async def test_an_empty_record_refuses_everyone(unconfigured) -> None:
    rest = await unconfigured.get("/destinations", headers=principal_header(OPERATOR_TOOLING))
    tools = await unconfigured.get("/mcp/", headers=principal_header(WORKBENCH))

    assert rest.status_code == 403
    assert tools.status_code == 403


@pytest.mark.db
async def test_the_probe_reaches_the_name_without_an_identity(guarded) -> None:
    named = await guarded.get("/")

    assert named.status_code == 200
    assert named.json()["service"] == "telegram-gateway"
    assert (await guarded.get("/ping")).status_code == 200
