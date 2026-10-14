"""move-from-azure-to-vps — trading tools on a server: reached by another service on the internal network with the
gateway's key, never from the edge, and never with a platform header someone wrote."""

from __future__ import annotations

import base64
import json

import httpx
import pytest
from pydantic import ValidationError

from trading_mcp.client import GatewayClient
from trading_mcp.config import Settings
from trading_mcp.server import build_http_app

from .conftest import BASE, KEY

EDGE = {"X-TC-Edge": "1"}


def _server_settings(**overrides) -> Settings:
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
    settings = _server_settings()
    gateway = GatewayClient(settings)
    # Exceptions inside the transport become a 500: this asks only whether the door let the request in.
    transport = httpx.ASGITransport(app=build_http_app(settings, gateway), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://tools") as client:
        yield client
    await gateway.aclose()


async def test_the_health_probe_needs_no_key(door: httpx.AsyncClient) -> None:
    assert (await door.get("/health")).status_code == 200


@pytest.mark.parametrize(
    "headers",
    [{}, {"X-Gateway-Key": "wrong"}, {**EDGE, "X-Gateway-Key": KEY}],
    ids=["no-key", "wrong-key", "key-through-the-edge"],
)
async def test_the_tool_surface_refuses_all_but_a_service_with_the_key(door, headers) -> None:
    assert (await door.post("/mcp", headers=headers, json={})).status_code == 401


async def test_a_platform_principal_header_opens_nothing(door: httpx.AsyncClient) -> None:
    blob = base64.b64encode(json.dumps({"claims": [{"typ": "azp", "val": "x"}]}).encode()).decode()
    headers = {"X-MS-CLIENT-PRINCIPAL": blob, "X-MS-CLIENT-PRINCIPAL-ID": "x"}
    assert (await door.post("/mcp", headers=headers, json={})).status_code == 401


async def test_a_service_with_the_key_gets_past_the_door(door: httpx.AsyncClient) -> None:
    response = await door.post("/mcp", headers={"X-Gateway-Key": KEY}, json={})
    assert response.status_code != 401


def test_server_mode_without_an_identity_requirement_refuses_to_start() -> None:
    with pytest.raises(ValidationError, match="REQUIRE_AUTHENTICATED_PRINCIPAL"):
        Settings(
            capital_gateway_url=BASE,
            capital_gateway_api_key=KEY,
            server_mode=True,
            _env_file=None,  # type: ignore[call-arg]
        )
