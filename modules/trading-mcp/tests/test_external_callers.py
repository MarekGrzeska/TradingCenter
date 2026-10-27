"""operator-mcp-access — the operator's own MCP client reaches the account from outside with a gateway token of a named
application, for an `admin`; and every write leaves a line before it is sent and one with what came of it."""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

import httpx
import pytest
import respx
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.lowlevel.server import request_ctx
from mcp.shared.context import RequestContext
from pydantic import ValidationError
from starlette.requests import Request
from tc_entra_auth import TokenVerifier

from trading_mcp.client import GatewayClient
from trading_mcp.config import Settings
from trading_mcp.server import build_http_app
from trading_mcp.trace import caller

from .conftest import BASE, KEY

EDGE = {"X-TC-Edge": "1"}
OPERATOR_APP = "claude-code-app-id"
TENANT = "11111111-2222-3333-4444-555555555555"

# What a token stands for in these tests: the verifier's signature check is `tc-entra-auth`'s, tested there once.
TOKENS: dict[str, dict[str, Any]] = {
    "operator": {"azp": OPERATOR_APP, "oid": "person-1", "roles": ["admin"]},
    "terminal": {"azp": "terminal-app-id", "oid": "person-1", "roles": ["admin"]},
    "viewer": {"azp": OPERATOR_APP, "oid": "person-2", "roles": ["viewer"]},
}


@pytest.fixture(autouse=True)
def _tokens_without_a_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    async def verify(self, token: str) -> dict[str, Any]:
        from tc_entra_auth import InvalidToken

        if token not in TOKENS:
            raise InvalidToken("not a token of this test")
        return TOKENS[token]

    monkeypatch.setattr(TokenVerifier, "verify", verify)


def _settings(**overrides: Any) -> Settings:
    return Settings(
        capital_gateway_url=BASE,
        capital_gateway_api_key=KEY,
        server_mode=True,
        require_authenticated_principal=True,
        _env_file=None,  # type: ignore[call-arg]
        **overrides,
    )


@pytest.fixture
async def door():
    settings = _settings(
        external_caller_application_ids=OPERATOR_APP,
        entra_tenant_id=TENANT,
        entra_audiences="api://tradingcenter-capital-gateway",
    )
    gateway = GatewayClient(settings)
    transport = httpx.ASGITransport(app=build_http_app(settings, gateway), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://tools") as client:
        yield client
    await gateway.aclose()


def _bearer(token: str) -> dict[str, str]:
    return {**EDGE, "Authorization": f"Bearer {token}"}


async def test_the_operators_application_gets_past_the_door(door: httpx.AsyncClient) -> None:
    response = await door.post("/mcp", headers=_bearer("operator"), json={})
    assert response.status_code not in (401, 403)


@pytest.mark.parametrize(("token", "status"), [("terminal", 403), ("viewer", 403), ("forged", 401)])
async def test_everyone_else_from_outside_is_refused(door: httpx.AsyncClient, token: str, status: int) -> None:
    assert (await door.post("/mcp", headers=_bearer(token), json={})).status_code == status


async def test_the_workbench_with_the_key_still_gets_in(door: httpx.AsyncClient) -> None:
    response = await door.post("/mcp", headers={"X-Gateway-Key": KEY}, json={})
    assert response.status_code not in (401, 403)


async def test_with_no_external_caller_named_a_token_opens_nothing() -> None:
    settings = _settings()
    gateway = GatewayClient(settings)
    transport = httpx.ASGITransport(app=build_http_app(settings, gateway), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://tools") as client:
        assert (await client.post("/mcp", headers=_bearer("operator"), json={})).status_code == 401
    await gateway.aclose()


def test_external_callers_without_a_tenant_refuse_to_start() -> None:
    with pytest.raises(ValidationError, match="ENTRA_TENANT_ID"):
        _settings(external_caller_application_ids=OPERATOR_APP)


def _request_with(headers: dict[str, str]) -> Request:
    raw = [(name.lower().encode(), value.encode()) for name, value in headers.items()]
    return Request({"type": "http", "method": "POST", "path": "/mcp", "headers": raw})


def test_the_trace_names_the_caller_the_door_wrote() -> None:
    blob = base64.b64encode(json.dumps({"claims": [{"typ": "azp", "val": OPERATOR_APP}]}).encode()).decode()
    request = _request_with({"X-MS-CLIENT-PRINCIPAL": blob, "X-MS-CLIENT-PRINCIPAL-ID": "person-1"})
    token = request_ctx.set(RequestContext(1, None, None, None, request=request))  # type: ignore[arg-type]
    try:
        assert caller() == (OPERATOR_APP, "person-1")
    finally:
        request_ctx.reset(token)


@respx.mock
async def test_a_write_is_traced_before_it_is_sent_and_after(server, caplog: pytest.LogCaptureFixture) -> None:
    sent: list[str] = []

    def gateway_answers(request: httpx.Request) -> httpx.Response:
        sent.append(" | ".join(r.getMessage() for r in caplog.records if r.name == "trading_mcp.trace"))
        return httpx.Response(200, json={"status": "FILLED", "id": "o1", "reference": "r1"})

    respx.post(f"{BASE}/orders").mock(side_effect=gateway_answers)
    with caplog.at_level(logging.INFO, logger="trading_mcp.trace"):
        await server.call_tool("place_order", {"symbol": "GOLD", "direction": "BUY", "size": 0.1})

    assert "account write sending: POST /orders" in sent[0]
    assert "outcome" not in sent[0]
    lines = [r.getMessage() for r in caplog.records if r.name == "trading_mcp.trace"]
    assert lines[-1].startswith("account write outcome: POST /orders answered status=FILLED")


@pytest.mark.parametrize(
    "answer",
    [httpx.ConnectError("down"), httpx.Response(200, text="<html>not json</html>")],
    ids=["unreachable", "unreadable"],
)
@respx.mock
async def test_a_write_whose_effect_is_unknown_is_traced_as_unknown(
    server, caplog: pytest.LogCaptureFixture, answer: Exception | httpx.Response
) -> None:
    respx.post(f"{BASE}/orders").mock(side_effect=[answer])
    with caplog.at_level(logging.INFO, logger="trading_mcp.trace"), pytest.raises(ToolError):
        await server.call_tool("place_order", {"symbol": "GOLD", "direction": "BUY", "size": 0.1})
    lines = [r.getMessage() for r in caplog.records if r.name == "trading_mcp.trace"]
    assert lines[-1].startswith("account write outcome: POST /orders unknown (")
