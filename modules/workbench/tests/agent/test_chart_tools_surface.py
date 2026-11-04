"""`/chart-tools/mcp` (`operator-mcp-access`): the conversation's drawing tools for the operator's own MCP client. The
tools' rules are tested in `test_drawings_tool.py`; here, that a drawing made over the wire lands and reads back."""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace

import httpx
import pytest
from starlette.applications import Starlette
from starlette.routing import Mount

from workbench.chart_tools import create_surface, serving

from .test_drawings_tool import FakeToolServer

pytestmark = pytest.mark.db

OPERATOR_APP = "operator-mcp-client"
MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def _door(application: str) -> dict[str, str]:
    """What `EdgeAuth` writes after it checked a token."""
    claims = {"claims": [{"typ": "azp", "val": application}]}
    return {"X-MS-CLIENT-PRINCIPAL": base64.b64encode(json.dumps(claims).encode()).decode()}


def _result(response: httpx.Response) -> dict:
    for line in response.text.splitlines():
        if line.startswith("data: "):
            return json.loads(line[len("data: ") :])
    raise AssertionError(f"no SSE data frame in: {response.text[:200]}")


async def _calls(pool, application: str, *calls: tuple[str, dict]) -> list[httpx.Response]:
    surface = create_surface()
    host = Starlette(routes=[Mount("/chart-tools", app=surface)])
    callers = SimpleNamespace(
        tool_caller_ids=frozenset({OPERATOR_APP}), require_authenticated_principal=True
    )
    answers: list[httpx.Response] = []
    async with (
        serving(surface, pool, FakeToolServer(), callers),  # type: ignore[arg-type]
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=host), base_url="https://api.example"
        ) as http,
    ):
        headers = {**MCP_HEADERS, **_door(application)}
        initialize = {
            "jsonrpc": "2.0",
            "id": 0,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "t", "version": "1"},
            },
        }
        opened = await http.post("/chart-tools/mcp", headers=headers, json=initialize)
        if opened.status_code != 200:
            return [opened]
        headers["mcp-session-id"] = opened.headers["mcp-session-id"]
        await http.post(
            "/chart-tools/mcp",
            headers=headers,
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        )
        for number, (name, arguments) in enumerate(calls, start=1):
            call = {"name": name, "arguments": arguments}
            answers.append(
                await http.post(
                    "/chart-tools/mcp",
                    headers=headers,
                    json={"jsonrpc": "2.0", "id": number, "method": "tools/call", "params": call},
                )
            )
    return answers


async def test_a_level_drawn_over_the_wire_reads_back_with_no_conversation_behind_it(pool) -> None:
    drawn, listed = await _calls(
        pool,
        OPERATOR_APP,
        ("draw_on_chart", {"symbol": "US100", "add": [{"kind": "level", "price": 27809, "label": "cel 1"}]}),
        ("list_chart_drawings", {"symbol": "US100"}),
    )

    assert _result(drawn)["result"]["isError"] is False
    drawings = json.loads(_result(listed)["result"]["content"][0]["text"])["drawings"]
    assert [(d["kind"], d["price"], d["label"]) for d in drawings] == [("level", 27809, "cel 1")]


async def test_a_refusal_arrives_as_an_error_the_client_can_read(pool) -> None:
    (answer,) = await _calls(pool, OPERATOR_APP, ("draw_on_chart", {"symbol": "US100"}))

    assert _result(answer)["result"]["isError"] is True
    assert "nothing to do" in _result(answer)["result"]["content"][0]["text"]


async def test_a_caller_off_the_list_is_refused_before_any_tool(pool) -> None:
    (answer,) = await _calls(pool, "terminal", ("list_chart_drawings", {"symbol": "US100"}))

    assert answer.status_code == 403
