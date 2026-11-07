"""specs/trading-mcp-tools and trading-mcp-upstream-access on the live instance (`live-account-trading`): what it
expects of the gateway before the port opens, which tools it leaves out, and how it says what it is moving."""

from __future__ import annotations

import httpx
import pytest
import respx
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import ValidationError

from trading_mcp.client import GatewayClient
from trading_mcp.config import Settings
from trading_mcp.errors import UnexpectedEnvironment
from trading_mcp.server import build_server

from .conftest import BASE, KEY
from .test_tool_surface import SURFACE_CEILING_CHARS, _surface


@pytest.fixture
def live_settings() -> Settings:
    return Settings(
        capital_gateway_url=BASE,
        capital_gateway_api_key=KEY,
        expected_environment="live",
        _env_file=None,  # type: ignore[call-arg]
    )


@pytest.fixture
async def live_gateway(live_settings: Settings):
    client = GatewayClient(live_settings)
    yield client
    await client.aclose()


@pytest.fixture
def live_server(live_settings: Settings, live_gateway: GatewayClient):
    return build_server(live_settings, live_gateway)


@respx.mock
async def test_a_live_instance_starts_in_front_of_a_live_gateway(live_gateway) -> None:
    respx.get(f"{BASE}/capabilities").mock(return_value=httpx.Response(200, json={"environment": "live"}))
    await live_gateway.ensure_expected_environment()


@pytest.mark.parametrize("answered", ["demo", None])
@respx.mock
async def test_a_live_instance_refuses_anything_else(live_gateway, answered) -> None:
    respx.get(f"{BASE}/capabilities").mock(return_value=httpx.Response(200, json={"environment": answered}))
    with pytest.raises(UnexpectedEnvironment, match="live"):
        await live_gateway.ensure_expected_environment()


def test_an_expectation_outside_the_two_is_refused() -> None:
    with pytest.raises(ValidationError):
        Settings(
            capital_gateway_url=BASE,
            capital_gateway_api_key=KEY,
            expected_environment="paper",  # type: ignore[arg-type]
            _env_file=None,  # type: ignore[call-arg]
        )


async def test_the_live_instance_neither_switches_nor_funds(live_server) -> None:
    names = {tool.name for tool in await live_server.list_tools()}
    assert "place_order" in names
    assert not names & {"switch_active_account", "top_up_demo_account"}


async def test_the_live_instance_says_it_is_real_money(live_server) -> None:
    assert "LIVE account" in live_server.instructions
    by_name = {tool.name: tool for tool in await live_server.list_tools()}
    assert by_name["place_order"].description.startswith("LIVE ACCOUNT")
    assert "never trimmed" in by_name["place_order"].description
    assert "demo" not in by_name["get_positions"].description


async def test_the_live_surface_stays_under_the_ceiling(live_server) -> None:
    assert len(_surface(await live_server.list_tools())) <= SURFACE_CEILING_CHARS


@respx.mock
async def test_a_limit_refusal_reaches_the_caller_naming_the_limit(live_server) -> None:
    detail = "refused by the live account's limits: size 2 of US100 is over the limit of 0.5 for one order"
    respx.post(f"{BASE}/orders").mock(return_value=httpx.Response(422, json={"detail": detail}))
    with pytest.raises(ToolError, match="over the limit of 0.5"):
        await live_server.call_tool("place_order", {"symbol": "US100", "direction": "BUY", "size": 2})
