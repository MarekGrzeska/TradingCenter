"""`/team-tools/mcp` (`operator-mcp-access`): the team tools for the operator's own MCP client, acting for the person the
door wrote — carried into the tool through a real stateful session, which is where a context variable set around the
HTTP request would have been lost."""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace

import httpx
import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from teams_tools.client import TeamsClient
from teams_tools.server import build_network_server
from workbench.team_tools import create_surface, serving

OPERATOR_APP = "operator-mcp-client"
MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


async def models(request: Request) -> JSONResponse:
    """The teams route `list_models` reads, answering with whose request it was."""
    return JSONResponse([{"asked_by": request.headers.get("x-ms-client-principal-id")}])


class _Tools:
    def __init__(self) -> None:
        self.client = TeamsClient(Starlette(routes=[Route("/models", models)]), operator_identity_optional=False)

    def network_server(self):
        return build_network_server(self.client)


def _door(application: str, person: str | None) -> dict[str, str]:
    """What `EdgeAuth` writes after it checked a token; the client's own copies are gone by then."""
    blob = base64.b64encode(json.dumps({"claims": [{"typ": "azp", "val": application}]}).encode()).decode()
    return {"X-MS-CLIENT-PRINCIPAL": blob, **({"X-MS-CLIENT-PRINCIPAL-ID": person} if person else {})}


def _result(response: httpx.Response) -> dict:
    for line in response.text.splitlines():
        if line.startswith("data: "):
            return json.loads(line[len("data: ") :])
    raise AssertionError(f"no SSE data frame in: {response.text[:200]}")


async def _list_models(application: str, person: str | None) -> httpx.Response:
    surface = create_surface()
    host = Starlette(routes=[Mount("/team-tools", app=surface)])
    tools = _Tools()
    callers = SimpleNamespace(tool_caller_ids=frozenset({OPERATOR_APP}), require_authenticated_principal=True)
    async with (
        serving(surface, tools, callers),  # type: ignore[arg-type]
        httpx.AsyncClient(transport=httpx.ASGITransport(app=host), base_url="https://api.example") as http,
    ):
        headers = {**MCP_HEADERS, **_door(application, person)}
        initialize = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}},
        }
        opened = await http.post("/team-tools/mcp", headers=headers, json=initialize)
        if opened.status_code != 200:
            return opened
        session = {"mcp-session-id": opened.headers["mcp-session-id"]}
        await http.post(
            "/team-tools/mcp", headers={**headers, **session}, json={"jsonrpc": "2.0", "method": "notifications/initialized"}
        )
        called = await http.post(
            "/team-tools/mcp",
            headers={**headers, **session},
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "list_models", "arguments": {}}},
        )
    await tools.client.aclose()
    return called


async def test_the_tool_acts_for_the_person_the_door_wrote() -> None:
    answered = _result(await _list_models(OPERATOR_APP, "person-1"))

    assert answered["result"]["structuredContent"]["result"] == [{"asked_by": "person-1"}]


async def test_without_a_person_the_tool_refuses_and_names_why() -> None:
    answered = _result(await _list_models(OPERATOR_APP, None))

    assert answered["result"]["isError"] is True
    assert "no operator identity" in answered["result"]["content"][0]["text"]


@pytest.mark.parametrize("application", ["terminal", "pocket"])
async def test_a_caller_off_the_list_is_refused_before_any_tool(application: str) -> None:
    assert (await _list_models(application, "person-1")).status_code == 403
