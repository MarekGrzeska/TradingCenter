"""The record under a prefix. Each module tests its own record standalone; this is the one fact the packages
share and the modules cannot see: a host mounting them leaves the prefix in the path the middleware reads."""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tc_runtime.caller_access import CallerAccess, Record

TERMINAL = "22222222-2222-2222-2222-222222222222"

RECORD = Record(
    open_paths=frozenset({"/ping"}),
    rest_paths=("/events", "/events/{event_id}"),
    tools_prefix="/mcp",
    starting_detail="still starting",
)


def _principal(application: str) -> dict[str, str]:
    blob = {"claims": [{"typ": "azp", "val": application}]}
    return {"x-ms-client-principal": base64.b64encode(json.dumps(blob).encode()).decode()}


def _mounted() -> TestClient:
    package = FastAPI()

    @package.get("/ping")
    async def ping() -> dict[str, str]:
        return {"status": "ok"}

    @package.get("/events/{event_id}")
    async def event(event_id: str) -> dict[str, str]:
        return {"event": event_id}

    package.add_middleware(CallerAccess, state=package.state, record=RECORD)
    package.state.settings = SimpleNamespace(
        require_authenticated_principal=True,
        tool_caller_ids=frozenset(),
        rest_caller_ids=frozenset({TERMINAL}),
    )
    host = FastAPI()
    host.mount("/archive", package)
    return TestClient(host)


def test_a_record_written_for_the_package_still_reads_under_the_hosts_prefix() -> None:
    client = _mounted()

    assert client.get("/archive/ping").status_code == 200
    assert client.get("/archive/events/e-1", headers=_principal(TERMINAL)).status_code == 200


def test_the_prefix_does_not_open_what_the_record_never_named() -> None:
    client = _mounted()

    refused = client.get("/archive/nowhere", headers=_principal(TERMINAL))
    assert refused.status_code == 403
    assert "not open to any caller" in refused.json()["detail"]
