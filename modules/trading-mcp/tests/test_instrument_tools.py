"""get_instrument_terms and size_for_margin — the terms an order is sized against."""

from __future__ import annotations

import httpx
import pytest
import respx
from mcp.server.fastmcp.exceptions import ToolError

BASE = "http://127.0.0.1:8010"

# US100 as the provider describes it: a 5% deposit, so 20x, in steps of 0.001.
US100 = {
    "symbol": "US100",
    "currency": "USD",
    "lot_size": 1,
    "margin_factor": 5,
    "margin_factor_unit": "PERCENTAGE",
    "min_deal_size": 0.1,
    "max_deal_size": 50000,
    "size_increment": 0.001,
}


def mock_terms(symbol: str = "US100", **overrides) -> None:
    respx.get(f"{BASE}/instruments/{symbol}/terms").mock(
        return_value=httpx.Response(200, json={**US100, "symbol": symbol, **overrides})
    )


@respx.mock
async def test_get_instrument_terms_carries_the_deposit_and_the_size_rules(server) -> None:
    mcp = server
    mock_terms()

    _content, structured = await mcp.call_tool("get_instrument_terms", {"symbol": "US100"})

    assert structured["margin_factor"] == 5
    assert structured["margin_factor_unit"] == "PERCENTAGE"
    assert structured["size_increment"] == 0.001


@respx.mock
async def test_get_instrument_terms_answers_no_price(server) -> None:
    mcp = server
    mock_terms()

    _content, structured = await mcp.call_tool("get_instrument_terms", {"symbol": "US100"})

    assert not any(field in structured for field in ("price", "bid", "ask", "offer"))


@respx.mock
async def test_get_instrument_terms_for_an_unknown_symbol_is_a_refusal(server) -> None:
    mcp = server
    respx.get(f"{BASE}/instruments/NOPE/terms").mock(
        return_value=httpx.Response(404, json={"detail": "unknown instrument 'NOPE'"})
    )

    with pytest.raises(ToolError) as err:
        await mcp.call_tool("get_instrument_terms", {"symbol": "NOPE"})

    assert "NOPE" in str(err.value)


@respx.mock
async def test_the_run_that_prompted_this_sized_against_the_contract_not_the_deposit(
    server,
) -> None:
    """The measured case: 2% of 95 306,83 USD into US100 at 30 174,5.

    The agent sent 0.0631704 — the deposit divided by the price, which is 2% of the
    account as *contract value* and one twentieth of it as deposit. Sized against the
    provider's 5%, the same 1 906,1366 USD is 1.263.
    """
    mcp = server
    mock_terms()

    _content, structured = await mcp.call_tool(
        "size_for_margin", {"symbol": "US100", "margin": 1906.1366, "price": 30174.5}
    )

    assert structured["size"] == 1.263
    assert structured["leverage"] == 20
    # Down to the step, so the deposit committed never exceeds the one asked for.
    assert structured["margin_used"] == pytest.approx(1905.5197, abs=0.001)
    assert structured["margin_used"] <= 1906.1366
    assert structured["notional"] == pytest.approx(38110.3935, abs=0.001)


@respx.mock
async def test_the_size_is_rounded_down_to_the_step_not_to_the_nearest(server) -> None:
    mcp = server
    # 100 of margin at 5% is 2000 of contract value; at a price of 3 that is 666.666…,
    # which rounds to 667 and floors to 666.
    mock_terms(min_deal_size=1, size_increment=1)

    _content, structured = await mcp.call_tool(
        "size_for_margin", {"symbol": "US100", "margin": 100, "price": 3}
    )

    assert structured["size"] == 666


@respx.mock
async def test_a_deposit_too_small_for_the_smallest_order_is_refused_with_both_numbers(
    server,
) -> None:
    mcp = server
    mock_terms()

    with pytest.raises(ToolError) as err:
        await mcp.call_tool(
            "size_for_margin", {"symbol": "US100", "margin": 10, "price": 30174.5}
        )

    message = str(err.value)
    assert "0.1" in message  # the smallest order the provider takes
    assert "150" in message  # and roughly what it would cost in margin


@respx.mock
async def test_a_deposit_over_the_largest_order_is_refused(server) -> None:
    mcp = server
    mock_terms(max_deal_size=1)

    with pytest.raises(ToolError) as err:
        await mcp.call_tool(
            "size_for_margin", {"symbol": "US100", "margin": 1906.1366, "price": 30174.5}
        )

    assert "1" in str(err.value)


@respx.mock
async def test_a_margin_unit_this_module_cannot_compute_with_is_refused_by_name(
    server,
) -> None:
    mcp = server
    mock_terms(margin_factor_unit="MULTIPLIER")

    with pytest.raises(ToolError) as err:
        await mcp.call_tool(
            "size_for_margin", {"symbol": "US100", "margin": 1906.1366, "price": 30174.5}
        )

    message = str(err.value)
    assert "MULTIPLIER" in message
    assert "PERCENTAGE" in message


@respx.mock
async def test_an_instrument_without_a_published_margin_requirement_is_refused(
    server,
) -> None:
    mcp = server
    mock_terms(margin_factor=None, margin_factor_unit=None)

    with pytest.raises(ToolError) as err:
        await mcp.call_tool(
            "size_for_margin", {"symbol": "US100", "margin": 100, "price": 30174.5}
        )

    assert "US100" in str(err.value)


@respx.mock
@pytest.mark.parametrize("bad", [{"margin": 0}, {"margin": -5}, {"price": 0}, {"price": -1}])
async def test_a_non_positive_margin_or_price_is_refused_before_the_gateway(
    server, bad: dict
) -> None:
    mcp = server
    route = respx.get(f"{BASE}/instruments/US100/terms")

    with pytest.raises(ToolError):
        await mcp.call_tool(
            "size_for_margin", {"symbol": "US100", "margin": 100, "price": 30174.5, **bad}
        )

    assert route.call_count == 0


@respx.mock
async def test_a_deposit_under_one_step_is_refused_rather_than_sized_at_zero(server) -> None:
    # No `min_deal_size` published, so nothing but this check stands between a deposit
    # too small to buy one step and an order for nothing.
    mcp = server
    mock_terms(min_deal_size=None)

    with pytest.raises(ToolError) as err:
        await mcp.call_tool(
            "size_for_margin", {"symbol": "US100", "margin": 0.5, "price": 30174.5}
        )

    assert "rounds down to nothing" in str(err.value)


@respx.mock
async def test_an_instrument_without_a_step_keeps_the_computed_size(server) -> None:
    mcp = server
    mock_terms(size_increment=None, min_deal_size=None)

    _content, structured = await mcp.call_tool(
        "size_for_margin", {"symbol": "US100", "margin": 100, "price": 4}
    )

    assert structured["size"] == 500  # 100 / 5% = 2000 of contract value, at 4
