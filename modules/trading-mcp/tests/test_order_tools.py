"""place_order, close_position, amend_stops, cancel_working_order — every write, and
specs/trading-mcp-execution's three outcomes: settled, unsettled, and never sent at
all.
"""

from __future__ import annotations

import httpx
import pytest
import respx
from mcp.server.fastmcp.exceptions import ToolError

BASE = "http://127.0.0.1:8010"


def _capabilities_demo() -> respx.Route:
    return respx.get(f"{BASE}/capabilities").mock(
        return_value=httpx.Response(200, json={"environment": "demo"})
    )


# --- place_order ---


@respx.mock
async def test_market_order_is_settled(server) -> None:
    mcp, gateway = server
    _capabilities_demo()
    order_route = respx.post(f"{BASE}/orders").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "FILLED",
                "id": "o1",
                "reference": "ref1",
                "symbol": "GOLD",
                "direction": "BUY",
                "size": 0.1,
                "level": 2400.0,
                "reason": None,
            },
        )
    )

    _content, structured = await mcp.call_tool(
        "place_order", {"symbol": "GOLD", "direction": "BUY", "size": 0.1}
    )

    assert structured["outcome"] == "settled"
    assert structured["status"] == "FILLED"
    body = order_route.calls.last.request.content
    assert b"MARKET" in body
    await gateway.aclose()


@respx.mock
async def test_limit_order_without_level_is_refused_before_any_request(server) -> None:
    mcp, gateway = server
    _capabilities_demo()
    order_route = respx.post(f"{BASE}/orders")

    with pytest.raises(ToolError, match="target level"):
        await mcp.call_tool(
            "place_order",
            {"symbol": "GOLD", "direction": "BUY", "size": 0.1, "order_type": "LIMIT"},
        )

    assert order_route.calls.call_count == 0
    await gateway.aclose()


@respx.mock
async def test_limit_order_with_level_is_accepted(server) -> None:
    mcp, gateway = server
    _capabilities_demo()
    order_route = respx.post(f"{BASE}/orders").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "WORKING",
                "id": "o2",
                "reference": "ref2",
                "symbol": "GOLD",
                "direction": "SELL",
                "size": 0.2,
                "level": 2500.0,
                "reason": None,
            },
        )
    )

    _content, structured = await mcp.call_tool(
        "place_order",
        {
            "symbol": "GOLD",
            "direction": "SELL",
            "size": 0.2,
            "order_type": "LIMIT",
            "level": 2500.0,
        },
    )

    assert structured["outcome"] == "settled"
    assert structured["status"] == "WORKING"
    assert order_route.called
    await gateway.aclose()


@respx.mock
async def test_pending_settlement_is_unsettled_not_filled(server) -> None:
    mcp, gateway = server
    _capabilities_demo()
    respx.post(f"{BASE}/orders").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "PENDING",
                "id": None,
                "reference": "ref3",
                "symbol": "GOLD",
                "direction": "BUY",
                "size": 0.1,
                "level": None,
                "reason": None,
            },
        )
    )

    _content, structured = await mcp.call_tool(
        "place_order", {"symbol": "GOLD", "direction": "BUY", "size": 0.1}
    )

    assert structured["outcome"] == "unsettled"
    assert structured["reference"] == "ref3"
    await gateway.aclose()


@respx.mock
async def test_provider_rejection_is_a_refusal_naming_the_symbol(server) -> None:
    mcp, gateway = server
    _capabilities_demo()
    respx.post(f"{BASE}/orders").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "REJECTED",
                "id": None,
                "reference": "ref4",
                "symbol": "NOTASYMBOL",
                "direction": "BUY",
                "size": 0.1,
                "level": None,
                "reason": "Instrument NOTASYMBOL not found",
            },
        )
    )

    with pytest.raises(ToolError, match="NOTASYMBOL"):
        await mcp.call_tool(
            "place_order", {"symbol": "NOTASYMBOL", "direction": "BUY", "size": 0.1}
        )
    await gateway.aclose()


@respx.mock
async def test_a_rejected_order_never_reads_as_an_access_failure(server) -> None:
    mcp, gateway = server
    _capabilities_demo()
    respx.post(f"{BASE}/orders").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "REJECTED",
                "id": None,
                "reference": "ref5",
                "symbol": "GOLD",
                "direction": "BUY",
                "size": 0.1,
                "level": None,
                "reason": "insufficient funds",
            },
        )
    )

    with pytest.raises(ToolError) as excinfo:
        await mcp.call_tool("place_order", {"symbol": "GOLD", "direction": "BUY", "size": 0.1})

    assert "access failure" not in str(excinfo.value)
    await gateway.aclose()


@respx.mock
async def test_a_timeout_is_an_access_failure_with_unknown_effect(server) -> None:
    mcp, gateway = server
    _capabilities_demo()
    respx.post(f"{BASE}/orders").mock(side_effect=httpx.ReadTimeout("timed out"))

    with pytest.raises(ToolError, match="access failure") as excinfo:
        await mcp.call_tool("place_order", {"symbol": "GOLD", "direction": "BUY", "size": 0.1})

    assert "unknown" in str(excinfo.value)
    assert "refused" not in str(excinfo.value)
    await gateway.aclose()


@respx.mock
async def test_a_5xx_write_is_an_access_failure_not_a_refusal(server) -> None:
    """Unlike a 4xx, a 5xx can happen after the provider already saw the request —
    grouped with access failures, not with a clean refusal (specs/
    trading-mcp-execution, "Moduł nie ponawia zlecenia po własnej awarii")."""
    mcp, gateway = server
    _capabilities_demo()
    respx.post(f"{BASE}/orders").mock(
        return_value=httpx.Response(503, json={"detail": "upstream trouble"})
    )

    with pytest.raises(ToolError, match="access failure"):
        await mcp.call_tool("place_order", {"symbol": "GOLD", "direction": "BUY", "size": 0.1})
    await gateway.aclose()


@respx.mock
async def test_a_write_is_never_retried_by_this_module(server) -> None:
    mcp, gateway = server
    _capabilities_demo()
    order_route = respx.post(f"{BASE}/orders").mock(
        return_value=httpx.Response(503, json={"detail": "upstream trouble"})
    )

    with pytest.raises(ToolError):
        await mcp.call_tool("place_order", {"symbol": "GOLD", "direction": "BUY", "size": 0.1})

    assert order_route.call_count == 1
    await gateway.aclose()


@respx.mock
async def test_a_4xx_validation_error_from_the_gateway_is_a_refusal(server) -> None:
    mcp, gateway = server
    _capabilities_demo()
    respx.post(f"{BASE}/orders").mock(
        return_value=httpx.Response(422, json={"detail": "size must be greater than 0"})
    )

    with pytest.raises(ToolError, match="size must be greater than 0"):
        await mcp.call_tool("place_order", {"symbol": "GOLD", "direction": "BUY", "size": 0.1})
    await gateway.aclose()


# --- close_position / cancel_working_order ---


@respx.mock
async def test_close_position_calls_the_right_id(server) -> None:
    mcp, gateway = server
    _capabilities_demo()
    route = respx.delete(f"{BASE}/positions/p1").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "CLOSED",
                "id": "p1",
                "reference": "ref6",
                "symbol": "GOLD",
                "direction": "BUY",
                "size": 0.1,
                "level": 2410.0,
                "reason": None,
            },
        )
    )

    _content, structured = await mcp.call_tool("close_position", {"position_id": "p1"})

    assert structured["outcome"] == "settled"
    assert route.called
    await gateway.aclose()


@respx.mock
async def test_cancel_working_order_calls_the_right_id(server) -> None:
    mcp, gateway = server
    _capabilities_demo()
    route = respx.delete(f"{BASE}/working-orders/w1").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "CANCELLED",
                "id": "w1",
                "reference": "ref7",
                "symbol": "GOLD",
                "direction": "SELL",
                "size": 0.1,
                "level": 2500.0,
                "reason": None,
            },
        )
    )

    _content, structured = await mcp.call_tool("cancel_working_order", {"order_id": "w1"})

    assert structured["outcome"] == "settled"
    assert route.called
    await gateway.aclose()


# --- amend_stops: the tri-state contract ---


@respx.mock
async def test_setting_one_stop_omits_the_other_from_the_request(server) -> None:
    mcp, gateway = server
    _capabilities_demo()
    route = respx.put(f"{BASE}/positions/p1").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "UPDATED",
                "id": "p1",
                "reference": "ref8",
                "symbol": "GOLD",
                "direction": "BUY",
                "size": 0.1,
                "level": 2400.0,
                "reason": None,
            },
        )
    )

    await mcp.call_tool("amend_stops", {"position_id": "p1", "stop_loss": 2350.0})

    import json

    sent = json.loads(route.calls.last.request.content)
    assert sent == {"stop_loss": 2350.0}
    await gateway.aclose()


@respx.mock
async def test_clearing_a_stop_sends_an_explicit_null(server) -> None:
    mcp, gateway = server
    _capabilities_demo()
    route = respx.put(f"{BASE}/positions/p1").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "UPDATED",
                "id": "p1",
                "reference": "ref9",
                "symbol": "GOLD",
                "direction": "BUY",
                "size": 0.1,
                "level": 2400.0,
                "reason": None,
            },
        )
    )

    await mcp.call_tool("amend_stops", {"position_id": "p1", "clear_take_profit": True})

    import json

    sent = json.loads(route.calls.last.request.content)
    assert sent == {"take_profit": None}
    await gateway.aclose()


async def test_amend_stops_with_nothing_to_change_is_refused(server) -> None:
    mcp, gateway = server

    with pytest.raises(ToolError, match="nothing to change"):
        await mcp.call_tool("amend_stops", {"position_id": "p1"})
    await gateway.aclose()


async def test_amend_stops_cannot_both_set_and_clear_the_same_stop(server) -> None:
    mcp, gateway = server

    with pytest.raises(ToolError, match="cannot both"):
        await mcp.call_tool(
            "amend_stops", {"position_id": "p1", "stop_loss": 2350.0, "clear_stop_loss": True}
        )
    await gateway.aclose()


@respx.mock
async def test_setting_both_stops_sends_both(server) -> None:
    mcp, gateway = server
    _capabilities_demo()
    route = respx.put(f"{BASE}/positions/p1").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "UPDATED",
                "id": "p1",
                "reference": "ref10",
                "symbol": "GOLD",
                "direction": "BUY",
                "size": 0.1,
                "level": 2400.0,
                "reason": None,
            },
        )
    )

    await mcp.call_tool(
        "amend_stops", {"position_id": "p1", "stop_loss": 2300.0, "take_profit": 2600.0}
    )

    import json

    sent = json.loads(route.calls.last.request.content)
    assert sent == {"stop_loss": 2300.0, "take_profit": 2600.0}
    await gateway.aclose()


# --- the demo guard is re-checked before every write ---


# --- the boundary between "your request was wrong" and "I could not ask" ---


@respx.mock
async def test_a_rejected_caller_key_is_an_access_failure_not_a_refusal(server) -> None:
    """A 401 is this module's own credential being turned away — nobody looked at the
    order. Reported as a refusal it would send an agent off re-editing an order that was
    never the problem (specs/trading-mcp-tools, "Odmowa narzędzia jest odróżnialna od
    awarii dostępu")."""
    mcp, gateway = server
    _capabilities_demo()
    respx.post(f"{BASE}/orders").mock(
        return_value=httpx.Response(401, json={"detail": "missing or invalid caller key"})
    )

    with pytest.raises(ToolError, match="access failure") as excinfo:
        await mcp.call_tool("place_order", {"symbol": "GOLD", "direction": "BUY", "size": 0.1})

    assert "unknown" in str(excinfo.value)
    await gateway.aclose()


@respx.mock
async def test_a_rate_limited_write_is_an_access_failure(server) -> None:
    mcp, gateway = server
    _capabilities_demo()
    respx.post(f"{BASE}/orders").mock(
        return_value=httpx.Response(429, json={"detail": "too many requests"})
    )

    with pytest.raises(ToolError, match="access failure"):
        await mcp.call_tool("place_order", {"symbol": "GOLD", "direction": "BUY", "size": 0.1})
    await gateway.aclose()


@respx.mock
async def test_a_404_on_a_position_stays_a_refusal(server) -> None:
    """The other side of the same boundary: an id that is gone is an answer about the
    request, and it names what to change."""
    mcp, gateway = server
    _capabilities_demo()
    respx.delete(f"{BASE}/positions/gone").mock(
        return_value=httpx.Response(404, json={"detail": "no such position"})
    )

    with pytest.raises(ToolError, match="refused") as excinfo:
        await mcp.call_tool("close_position", {"position_id": "gone"})

    assert "access failure" not in str(excinfo.value)
    await gateway.aclose()


# --- arguments a MARKET order cannot carry ---


@respx.mock
async def test_a_market_order_with_a_level_is_refused_before_any_request(server) -> None:
    """capital-gateway drops `level` and `good_till` from a MARKET order without a word,
    and the `level` that comes back is the fill price — so an agent that meant "buy, but
    not above this" would be filled anywhere and read nothing about it."""
    mcp, gateway = server
    _capabilities_demo()
    order_route = respx.post(f"{BASE}/orders")

    with pytest.raises(ToolError, match="ignored") as excinfo:
        await mcp.call_tool(
            "place_order",
            {"symbol": "GOLD", "direction": "BUY", "size": 0.1, "level": 2400.0},
        )

    assert "LIMIT" in str(excinfo.value)
    assert order_route.calls.call_count == 0
    await gateway.aclose()


@respx.mock
async def test_a_market_order_with_good_till_is_refused_and_names_it(server) -> None:
    mcp, gateway = server
    _capabilities_demo()
    order_route = respx.post(f"{BASE}/orders")

    with pytest.raises(ToolError, match="good_till"):
        await mcp.call_tool(
            "place_order",
            {
                "symbol": "GOLD",
                "direction": "BUY",
                "size": 0.1,
                "good_till": "2026-08-18T10:00:00Z",
            },
        )

    assert order_route.calls.call_count == 0
    await gateway.aclose()


# --- the demo check's own failures are this module's, and nothing was sent ---


@respx.mock
async def test_a_write_costs_one_round_trip(server) -> None:
    """The demo check ran in front of every write until 18 August 2026, behind a cache
    any error invalidated — so one 503 made every later write cost two rounds for the
    life of the process. It runs once now, before the port opens
    (specs/trading-mcp-upstream-access, "Moduł pracuje wyłącznie na rachunku
    demonstracyjnym")."""
    mcp, gateway = server
    capabilities = respx.get(f"{BASE}/capabilities")
    respx.post(f"{BASE}/orders").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "FILLED",
                "id": "o9",
                "reference": "ref9",
                "symbol": "GOLD",
                "direction": "BUY",
                "size": 0.1,
                "level": 2400.0,
                "reason": None,
            },
        )
    )

    await mcp.call_tool("place_order", {"symbol": "GOLD", "direction": "BUY", "size": 0.1})
    await mcp.call_tool("place_order", {"symbol": "GOLD", "direction": "BUY", "size": 0.1})

    assert capabilities.calls.call_count == 0
    await gateway.aclose()
