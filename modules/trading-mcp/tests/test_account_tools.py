"""get_positions, get_working_orders, get_balance — reading the account."""

from __future__ import annotations

import httpx
import pytest
import respx
from mcp.server.fastmcp.exceptions import ToolError

BASE = "http://127.0.0.1:8010"


@respx.mock
async def test_get_positions_maps_every_field(server) -> None:
    mcp, gateway = server
    respx.get(f"{BASE}/positions").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "p1",
                    "symbol": "GOLD",
                    "direction": "BUY",
                    "size": 0.5,
                    "open_level": 2400.0,
                    "pnl": 12.3,
                    "currency": "USD",
                }
            ],
        )
    )

    _content, structured = await mcp.call_tool("get_positions", {})

    assert structured["result"][0]["symbol"] == "GOLD"
    assert structured["result"][0]["pnl"] == 12.3
    await gateway.aclose()


@respx.mock
async def test_get_positions_empty_account_answers_empty_list(server) -> None:
    mcp, gateway = server
    respx.get(f"{BASE}/positions").mock(return_value=httpx.Response(200, json=[]))

    _content, structured = await mcp.call_tool("get_positions", {})

    assert structured["result"] == []
    await gateway.aclose()


@respx.mock
async def test_get_working_orders_maps_every_field(server) -> None:
    mcp, gateway = server
    respx.get(f"{BASE}/working-orders").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "w1",
                    "symbol": "GOLD",
                    "direction": "SELL",
                    "size": 1.0,
                    "order_type": "LIMIT",
                    "level": 2500.0,
                    "good_till": None,
                    "currency": "USD",
                }
            ],
        )
    )

    _content, structured = await mcp.call_tool("get_working_orders", {})

    assert structured["result"][0]["order_type"] == "LIMIT"
    await gateway.aclose()


@respx.mock
async def test_get_balance_reads_the_active_account(server) -> None:
    mcp, gateway = server
    respx.get(f"{BASE}/accounts").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "a1",
                    "name": "demo-secondary",
                    "currency": "USD",
                    "balance": 1000.0,
                    "available": 900.0,
                    "pnl": -5.0,
                    "active": False,
                },
                {
                    "id": "a2",
                    "name": "demo-main",
                    "currency": "USD",
                    "balance": 5000.0,
                    "available": 4800.0,
                    "pnl": 42.0,
                    "active": True,
                },
            ],
        )
    )

    _content, structured = await mcp.call_tool("get_balance", {})

    assert structured["account_id"] == "a2"
    assert structured["balance"] == 5000.0
    await gateway.aclose()


@respx.mock
async def test_get_balance_refuses_when_no_account_is_active(server) -> None:
    mcp, gateway = server
    respx.get(f"{BASE}/accounts").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "a1",
                    "name": "demo",
                    "currency": "USD",
                    "balance": 1000.0,
                    "available": 900.0,
                    "pnl": 0.0,
                    "active": False,
                }
            ],
        )
    )

    with pytest.raises(ToolError, match="active account"):
        await mcp.call_tool("get_balance", {})
    await gateway.aclose()


@respx.mock
async def test_a_gateway_timeout_is_an_access_failure_not_a_refusal(server) -> None:
    mcp, gateway = server
    respx.get(f"{BASE}/positions").mock(side_effect=httpx.ReadTimeout("timed out"))

    with pytest.raises(ToolError, match="access failure"):
        await mcp.call_tool("get_positions", {})
    await gateway.aclose()


@respx.mock
async def test_a_gateway_refusal_names_the_detail(server) -> None:
    mcp, gateway = server
    respx.get(f"{BASE}/positions").mock(
        return_value=httpx.Response(422, json={"detail": "bad request"})
    )

    with pytest.raises(ToolError, match="bad request"):
        await mcp.call_tool("get_positions", {})
    await gateway.aclose()
