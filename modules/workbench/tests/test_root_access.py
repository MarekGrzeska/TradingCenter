"""The root's own caller record: since the door to Telegram moved in, Easy Auth admits the operator's `az` to this
whole process, and only `/telegram` may answer it. Fail-closed, so every way through is walked here."""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace

import httpx
import pytest
from starlette.types import Receive, Scope, Send
from tc_runtime.caller_access import in_process

from workbench.root_access import RootCallers

TERMINAL = "terminal-app-id"
AZURE_CLI = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"


async def _reached(scope: Scope, receive: Receive, send: Send) -> None:
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"reached"})


def _principal(application: str) -> dict[str, str]:
    """The header Easy Auth writes, carrying the application the token was issued to."""
    blob = {"claims": [{"typ": "azp", "val": application}]}
    return {"X-MS-CLIENT-PRINCIPAL": base64.b64encode(json.dumps(blob).encode()).decode()}


def _client(*, require: bool = True, started: bool = True, in_this_process: bool = False):
    state = SimpleNamespace()
    if started:
        state.settings = SimpleNamespace(
            require_authenticated_principal=require, rest_caller_application_ids=TERMINAL
        )
    guarded = RootCallers(_reached, state=state, package_prefixes=frozenset({"/telegram"}))
    app = in_process(guarded, "a test") if in_this_process else guarded
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://workbench")


@pytest.mark.parametrize(
    ("path", "headers", "status"),
    [
        ("/sessions", _principal(TERMINAL), 200),
        ("/sessions", _principal(AZURE_CLI), 403),
        ("/sessions", {}, 401),
        # A package's path is its own record's to decide, `az` included.
        ("/telegram/bots", _principal(AZURE_CLI), 200),
        # A prefix is a whole segment: this is a root path that merely starts with the same letters.
        ("/telegramish", _principal(AZURE_CLI), 403),
        ("/health", {}, 200),
    ],
)
async def test_the_root_answers_only_the_listed_applications(path, headers, status) -> None:
    async with _client() as client:
        assert (await client.get(path, headers=headers)).status_code == status


async def test_a_process_that_has_not_started_refuses_rather_than_admits() -> None:
    async with _client(started=False) as client:
        assert (await client.get("/sessions", headers=_principal(TERMINAL))).status_code == 503


async def test_this_process_asking_itself_is_admitted() -> None:
    async with _client(in_this_process=True) as client:
        assert (await client.get("/teams")).status_code == 200


async def test_local_work_with_nothing_in_front_is_admitted() -> None:
    async with _client(require=False) as client:
        assert (await client.get("/sessions")).status_code == 200
