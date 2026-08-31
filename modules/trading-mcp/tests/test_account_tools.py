"""Reading the account, and choosing and funding the one being read."""

from __future__ import annotations

import httpx
import pytest
import respx
from mcp.server.fastmcp.exceptions import ToolError

BASE = "http://127.0.0.1:8010"


@respx.mock
async def test_get_positions_maps_every_field(server) -> None:
    mcp = server
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


@respx.mock
async def test_get_positions_empty_account_answers_empty_list(server) -> None:
    mcp = server
    respx.get(f"{BASE}/positions").mock(return_value=httpx.Response(200, json=[]))

    _content, structured = await mcp.call_tool("get_positions", {})

    assert structured["result"] == []


@respx.mock
async def test_get_working_orders_maps_every_field(server) -> None:
    mcp = server
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


@respx.mock
async def test_get_balance_reads_the_active_account(server) -> None:
    mcp = server
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


@respx.mock
async def test_get_balance_refuses_when_no_account_is_active(server) -> None:
    mcp = server
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


@respx.mock
async def test_a_gateway_timeout_is_an_access_failure_not_a_refusal(server) -> None:
    mcp = server
    respx.get(f"{BASE}/positions").mock(side_effect=httpx.ReadTimeout("timed out"))

    with pytest.raises(ToolError, match="access failure"):
        await mcp.call_tool("get_positions", {})


@respx.mock
async def test_a_gateway_refusal_names_the_detail(server) -> None:
    mcp = server
    respx.get(f"{BASE}/positions").mock(
        return_value=httpx.Response(422, json={"detail": "bad request"})
    )

    with pytest.raises(ToolError, match="bad request"):
        await mcp.call_tool("get_positions", {})


@respx.mock
async def test_a_read_the_gateway_would_not_serve_is_an_access_failure(server) -> None:
    """A 401 or a 503 on a read means the read never happened. Answered as a refusal it would read as
    an answer *about the account*, which these tools must never let a caller believe."""
    mcp = server
    respx.get(f"{BASE}/positions").mock(
        return_value=httpx.Response(401, json={"detail": "missing or invalid caller key"})
    )

    with pytest.raises(ToolError, match="access failure") as excinfo:
        await mcp.call_tool("get_positions", {})

    assert "Nothing was read" in str(excinfo.value)


_ACCOUNTS = [
    {
        "id": "a1",
        "name": "EUR",
        "currency": "EUR",
        "balance": 51000.0,
        "available": 51000.0,
        "pnl": 0.0,
        "active": False,
    },
    {
        "id": "a2",
        "name": "demo2",
        "currency": "USD",
        "balance": 9000.0,
        "available": 8800.0,
        "pnl": -12.0,
        "active": True,
    },
]


@respx.mock
async def test_list_accounts_names_the_active_one(server) -> None:
    # specs/trading-mcp-tools, "Model wylicza konta"
    mcp = server
    respx.get(f"{BASE}/accounts").mock(return_value=httpx.Response(200, json=_ACCOUNTS))

    _content, structured = await mcp.call_tool("list_accounts", {})

    rows = structured["result"]
    assert [row["id"] for row in rows] == ["a1", "a2"]
    assert [row["active"] for row in rows] == [False, True]


@respx.mock
async def test_switching_the_account_answers_with_the_one_now_active(server) -> None:
    # specs/trading-mcp-tools, "Model przełącza konto"
    mcp = server
    sent: list[dict] = []

    def record(request: httpx.Request) -> httpx.Response:
        import json as _json

        sent.append(_json.loads(request.content))
        return httpx.Response(200, json={**_ACCOUNTS[0], "active": True})

    respx.put(f"{BASE}/accounts/active").mock(side_effect=record)

    _content, structured = await mcp.call_tool("switch_active_account", {"account_id": "a1"})

    assert sent == [{"account_id": "a1"}]
    assert structured["id"] == "a1"
    assert structured["active"] is True


async def test_the_switch_tool_warns_that_it_drops_the_stream(server) -> None:
    """specs/trading-mcp-tools: the gap this call leaves is in collected candles, not in
    the conversation, so nothing the model sees afterwards would tell it."""
    mcp = server
    by_name = {t.name: t for t in await mcp.list_tools()}
    description = (by_name["switch_active_account"].description or "").lower()

    assert "stream" in description


@respx.mock
async def test_topping_up_answers_with_the_account_after_the_move(server) -> None:
    # specs/trading-mcp-tools, "Model koryguje saldo konta demo"
    mcp = server
    sent: list[dict] = []

    def record(request: httpx.Request) -> httpx.Response:
        import json as _json

        sent.append(_json.loads(request.content))
        return httpx.Response(200, json={**_ACCOUNTS[1], "balance": 14000.0})

    respx.post(f"{BASE}/accounts/top-up").mock(side_effect=record)

    _content, structured = await mcp.call_tool("top_up_demo_account", {"amount": 5000})

    assert sent == [{"amount": 5000.0}]
    assert structured["balance"] == 14000.0


@respx.mock
async def test_taking_funds_away_is_the_same_call(server) -> None:
    mcp = server
    sent: list[dict] = []

    def record(request: httpx.Request) -> httpx.Response:
        import json as _json

        sent.append(_json.loads(request.content))
        return httpx.Response(200, json={**_ACCOUNTS[1], "balance": 4000.0})

    respx.post(f"{BASE}/accounts/top-up").mock(side_effect=record)

    _content, structured = await mcp.call_tool("top_up_demo_account", {"amount": -5000})

    assert sent == [{"amount": -5000.0}]
    assert structured["balance"] == 4000.0


@respx.mock
async def test_a_refused_top_up_says_why_and_is_not_an_access_failure(server) -> None:
    """specs/trading-mcp-tools, "Dostawca odmawia korekty salda" — the ceiling and the
    daily count are the provider's, and its reason is what the model has to act on."""
    mcp = server
    respx.post(f"{BASE}/accounts/top-up").mock(
        return_value=httpx.Response(
            400, json={"detail": "capital.com refused: top up balance exceeded"}
        )
    )

    with pytest.raises(ToolError, match="refused") as excinfo:
        await mcp.call_tool("top_up_demo_account", {"amount": 400000})

    message = str(excinfo.value)
    assert "balance exceeded" in message
    assert "access failure" not in message


@respx.mock
async def test_a_top_up_the_gateway_never_served_is_an_access_failure(server) -> None:
    mcp = server
    respx.post(f"{BASE}/accounts/top-up").mock(
        return_value=httpx.Response(401, json={"detail": "missing or invalid caller key"})
    )

    with pytest.raises(ToolError, match="access failure") as excinfo:
        await mcp.call_tool("top_up_demo_account", {"amount": 100})

    assert "read the accounts" in str(excinfo.value)
