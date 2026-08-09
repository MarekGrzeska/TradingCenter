from __future__ import annotations

import json

import httpx
import pytest
import respx

from capital_gateway.adapter import CapitalAdapter
from capital_gateway.client import CapitalClient
from capital_gateway.config import DEMO_BASE_URL, Settings
from capital_gateway.dtos import (
    AssetClass,
    Direction,
    OrderStatus,
    OrderType,
    PlaceOrderRequest,
    Resolution,
    UpdatePositionRequest,
)
from capital_gateway.errors import GatewayError
from tests.conftest import load_fixture

API = f"{DEMO_BASE_URL}/api/v1"


@pytest.fixture
def adapter() -> CapitalAdapter:
    client = CapitalClient(
        Settings(
            capital_api_key="k",
            capital_identifier="me@example.com",
            capital_password="p",
            gateway_api_key="g",
            _env_file=None,
        )
    )
    return CapitalAdapter(client)


def mock_session(account_id: str = "acc-1") -> None:
    respx.post(f"{API}/session").mock(
        return_value=httpx.Response(200, headers={"CST": "c", "X-SECURITY-TOKEN": "t"}, json={})
    )
    respx.get(f"{API}/session").mock(
        return_value=httpx.Response(200, json={"accountId": account_id})
    )


def mock_navigation() -> None:
    respx.get(f"{API}/marketnavigation").mock(
        return_value=httpx.Response(200, json=load_fixture("navigation_root.json"))
    )
    respx.get(f"{API}/marketnavigation/hierarchy_v1.commodities").mock(
        return_value=httpx.Response(200, json=load_fixture("navigation_commodities.json"))
    )
    respx.get(f"{API}/marketnavigation/hierarchy_v1.commodities.metals").mock(
        return_value=httpx.Response(200, json=load_fixture("navigation_metals.json"))
    )
    # The second root branch is unreadable on purpose — see the traversal test below.
    respx.get(f"{API}/marketnavigation/hierarchy_v1.indices").mock(
        return_value=httpx.Response(500, text="boom")
    )


# --- reads ---


@respx.mock
async def test_searching_returns_matching_instruments(adapter: CapitalAdapter) -> None:
    mock_session()
    respx.get(f"{API}/markets").mock(
        return_value=httpx.Response(200, json=load_fixture("search_gold.json"))
    )

    found = await adapter.search_instruments("gold")

    assert found
    assert any(i.symbol == "GOLD" for i in found)
    assert all(i.provider == "capital.com" for i in found)
    await adapter.aclose()


@respx.mock
async def test_switching_to_a_known_account_makes_it_active(adapter: CapitalAdapter) -> None:
    raw = load_fixture("accounts.json")
    target = raw["accounts"][1]["accountId"]
    mock_session(account_id=raw["accounts"][0]["accountId"])
    switch = respx.put(f"{API}/session").mock(return_value=httpx.Response(200, json={}))
    respx.get(f"{API}/accounts").mock(return_value=httpx.Response(200, json=raw))

    account = await adapter.set_active_account(target)

    assert account.id == target
    assert account.active is True
    assert json.loads(switch.calls.last.request.content) == {"accountId": target}
    await adapter.aclose()


@respx.mock
async def test_accounts_mark_the_active_one(adapter: CapitalAdapter) -> None:
    raw = load_fixture("accounts.json")
    mock_session(account_id=raw["accounts"][0]["accountId"])
    respx.get(f"{API}/accounts").mock(return_value=httpx.Response(200, json=raw))

    accounts = await adapter.list_accounts()

    assert sum(a.active for a in accounts) == 1
    assert accounts[0].active is True
    await adapter.aclose()


@respx.mock
async def test_switching_to_an_unknown_account_leaves_the_current_one(
    adapter: CapitalAdapter,
) -> None:
    mock_session()
    respx.put(f"{API}/session").mock(return_value=httpx.Response(400, json={}))

    with pytest.raises(GatewayError) as err:
        await adapter.set_active_account("nope")

    assert err.value.status_code == 400
    assert "nope" in err.value.message
    await adapter.aclose()


@respx.mock
async def test_the_traversal_dedupes_and_survives_a_bad_branch(adapter: CapitalAdapter) -> None:
    mock_session()
    mock_navigation()

    page = await adapter.list_instruments(max_nodes=100)

    # GOLD hangs under both commodities and metals; one instrument, not two.
    assert sorted(i.symbol for i in page.instruments) == ["GOLD", "OIL_CRUDE", "SILVER"]
    assert page.truncated is False
    # The 500 on the indices branch cost that branch, not the catalogue.
    assert page.count == 3
    await adapter.aclose()


@respx.mock
async def test_a_cut_short_traversal_says_so(adapter: CapitalAdapter) -> None:
    mock_session()
    mock_navigation()

    page = await adapter.list_instruments(max_nodes=1)

    # Without the flag this is indistinguishable from a catalogue that really is that
    # small.
    assert page.truncated is True
    assert page.nodes_visited == 1
    await adapter.aclose()


def mock_mixed_navigation() -> None:
    """A tree with two asset classes in it.

    Kept apart from `mock_navigation` rather than folded into it: the traversal tests
    below assert on exact catalogue contents, and a sieve tested against a tree of one
    class would pass while letting everything through.
    """
    respx.get(f"{API}/marketnavigation").mock(
        return_value=httpx.Response(
            200,
            json={
                "nodes": [
                    {"id": "hierarchy_v1.commodities", "name": "Commodities"},
                    {"id": "hierarchy_v1.shares", "name": "Shares"},
                ]
            },
        )
    )
    respx.get(f"{API}/marketnavigation/hierarchy_v1.commodities").mock(
        return_value=httpx.Response(200, json=load_fixture("navigation_commodities.json"))
    )
    respx.get(f"{API}/marketnavigation/hierarchy_v1.commodities.metals").mock(
        return_value=httpx.Response(200, json=load_fixture("navigation_metals.json"))
    )
    respx.get(f"{API}/marketnavigation/hierarchy_v1.shares").mock(
        return_value=httpx.Response(200, json=load_fixture("navigation_shares.json"))
    )


@respx.mock
async def test_one_asset_class_comes_back_without_the_others(adapter: CapitalAdapter) -> None:
    mock_session()
    mock_mixed_navigation()

    page = await adapter.list_instruments(max_nodes=100, asset_class=AssetClass.SHARES)

    assert sorted(i.symbol for i in page.instruments) == ["AAPL", "MSFT"]
    # `count` is what came back, not what the tree held — a consumer sizing a list off
    # it would otherwise be told about instruments it cannot see.
    assert page.count == 2
    assert page.truncated is False
    await adapter.aclose()


@respx.mock
async def test_filtering_by_class_still_walks_the_whole_tree(adapter: CapitalAdapter) -> None:
    """The sieve is on markets, not on branches.

    A walk that guessed a branch's class from its name would be cheaper and would drop
    instruments filed somewhere the name did not suggest.
    """
    mock_session()
    mock_mixed_navigation()

    unfiltered = await adapter.list_instruments(max_nodes=100)
    filtered = await adapter.list_instruments(max_nodes=100, asset_class=AssetClass.SHARES)

    assert filtered.nodes_visited == unfiltered.nodes_visited
    await adapter.aclose()


@respx.mock
async def test_a_class_nothing_matches_is_an_empty_catalogue_not_an_error(
    adapter: CapitalAdapter,
) -> None:
    mock_session()
    mock_mixed_navigation()

    page = await adapter.list_instruments(max_nodes=100, asset_class=AssetClass.CRYPTO)

    assert page.instruments == []
    assert page.count == 0
    await adapter.aclose()


@respx.mock
async def test_a_filtered_walk_cut_short_still_says_so(adapter: CapitalAdapter) -> None:
    mock_session()
    mock_mixed_navigation()

    page = await adapter.list_instruments(max_nodes=1, asset_class=AssetClass.SHARES)

    # The filter narrows what comes back; it does not turn a partial walk into a
    # complete one, which is the mistake that would matter here.
    assert page.truncated is True
    await adapter.aclose()


@respx.mock
async def test_candles_come_back_in_the_requested_resolution(adapter: CapitalAdapter) -> None:
    mock_session()
    respx.get(f"{API}/prices/GOLD").mock(
        return_value=httpx.Response(200, json=load_fixture("prices_gold.json"))
    )

    candles = await adapter.get_candles("GOLD", Resolution.MINUTE_5, 3)

    assert len(candles) == 3
    assert all(c.resolution is Resolution.MINUTE_5 for c in candles)
    await adapter.aclose()


@respx.mock
async def test_an_unknown_symbol_is_a_404_not_a_502(adapter: CapitalAdapter) -> None:
    mock_session()
    respx.get(f"{API}/prices/NOPE").mock(
        return_value=httpx.Response(404, json={"errorCode": "error.not-found.epic"})
    )

    with pytest.raises(GatewayError) as err:
        await adapter.get_candles("NOPE", Resolution.MINUTE, 10)

    assert err.value.status_code == 404
    await adapter.aclose()


@respx.mock
async def test_a_rate_limited_read_raises_instead_of_reaching_a_mapper(
    adapter: CapitalAdapter,
) -> None:
    mock_session()
    respx.get(f"{API}/positions").mock(
        return_value=httpx.Response(429, json={"errorCode": "error.too-many.requests"})
    )

    # Without the status check this payload reaches position_from_raw and dies on a
    # missing key, which reads like a bug here rather than a refusal there.
    with pytest.raises(GatewayError) as err:
        await adapter.list_positions()

    assert "429" in err.value.message
    await adapter.aclose()


# --- trading ---


@respx.mock
async def test_open_positions_are_readable(adapter: CapitalAdapter) -> None:
    mock_session()
    raw = load_fixture("positions.json")
    respx.get(f"{API}/positions").mock(return_value=httpx.Response(200, json=raw))

    positions = await adapter.list_positions()

    assert len(positions) == len(raw["positions"])
    assert all(p.id and p.symbol for p in positions)
    await adapter.aclose()


@respx.mock
async def test_no_positions_is_an_empty_list_not_an_error(adapter: CapitalAdapter) -> None:
    mock_session()
    respx.get(f"{API}/positions").mock(return_value=httpx.Response(200, json={"positions": []}))

    # A flat account is a normal state, and a caller polling it should not have to catch
    # an exception to learn that.
    assert await adapter.list_positions() == []
    await adapter.aclose()


@respx.mock
async def test_working_orders_are_listed(adapter: CapitalAdapter) -> None:
    mock_session()
    raw = load_fixture("working_orders.json")
    respx.get(f"{API}/workingorders").mock(return_value=httpx.Response(200, json=raw))

    orders = await adapter.list_working_orders()

    assert len(orders) == len(raw["workingOrders"])
    first = orders[0]
    assert first.id and first.symbol
    assert first.order_type in (OrderType.LIMIT, OrderType.STOP)
    await adapter.aclose()


@respx.mock
async def test_a_market_order_settles_as_filled(adapter: CapitalAdapter) -> None:
    mock_session()
    respx.post(f"{API}/positions").mock(
        return_value=httpx.Response(200, json=load_fixture("create_position.json"))
    )
    respx.get(url__startswith=f"{API}/confirms/").mock(
        return_value=httpx.Response(200, json=load_fixture("confirm_open.json"))
    )

    order = await adapter.place_order(
        PlaceOrderRequest(symbol="GOLD", direction=Direction.BUY, size=0.01)
    )

    assert order.status is OrderStatus.FILLED
    await adapter.aclose()


@respx.mock
async def test_a_resting_order_goes_to_working_orders_and_settles_as_working(
    adapter: CapitalAdapter,
) -> None:
    mock_session()
    created = respx.post(f"{API}/workingorders").mock(
        return_value=httpx.Response(200, json=load_fixture("wo_create.json"))
    )
    respx.get(url__startswith=f"{API}/confirms/").mock(
        return_value=httpx.Response(200, json=load_fixture("wo_confirm.json"))
    )

    order = await adapter.place_order(
        PlaceOrderRequest(
            symbol="GOLD",
            direction=Direction.BUY,
            size=0.01,
            order_type=OrderType.LIMIT,
            level=1900.0,
            stop_loss=1850.0,
        )
    )

    assert order.status is OrderStatus.WORKING
    sent = json.loads(created.calls.last.request.content)
    assert sent["type"] == "LIMIT"
    assert sent["level"] == 1900.0
    assert sent["stopLevel"] == 1850.0
    await adapter.aclose()


@respx.mock
async def test_an_amendment_sends_only_the_named_stop(adapter: CapitalAdapter) -> None:
    mock_session()
    updated = respx.put(f"{API}/positions/deal-1").mock(
        return_value=httpx.Response(200, json={"dealReference": "ref-1"})
    )
    respx.get(url__startswith=f"{API}/confirms/").mock(
        return_value=httpx.Response(200, json=load_fixture("confirm_open.json"))
    )

    await adapter.update_position("deal-1", UpdatePositionRequest(stop_loss=1800.0))

    sent = json.loads(updated.calls.last.request.content)
    assert sent == {"stopLevel": 1800.0}
    # profitLevel absent, not null: sending null here removes a take-profit the caller
    # never mentioned.
    assert "profitLevel" not in sent
    await adapter.aclose()


@respx.mock
async def test_clearing_a_stop_sends_null(adapter: CapitalAdapter) -> None:
    mock_session()
    updated = respx.put(f"{API}/positions/deal-1").mock(
        return_value=httpx.Response(200, json={"dealReference": "ref-1"})
    )
    respx.get(url__startswith=f"{API}/confirms/").mock(
        return_value=httpx.Response(200, json=load_fixture("confirm_open.json"))
    )

    await adapter.update_position("deal-1", UpdatePositionRequest(take_profit=None))

    assert json.loads(updated.calls.last.request.content) == {"profitLevel": None}
    await adapter.aclose()


@respx.mock
async def test_a_refused_deal_is_rejected_with_the_provider_reason(
    adapter: CapitalAdapter,
) -> None:
    mock_session()
    respx.post(f"{API}/positions").mock(
        return_value=httpx.Response(400, json={"errorCode": "error.invalid.size"})
    )

    order = await adapter.place_order(
        PlaceOrderRequest(symbol="GOLD", direction=Direction.BUY, size=0.01)
    )

    # No dealReference at all: refused before the deal existed.
    assert order.status is OrderStatus.REJECTED
    assert order.reason == "error.invalid.size"
    await adapter.aclose()


@respx.mock
async def test_a_deal_that_never_settles_is_pending_never_filled(
    adapter: CapitalAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("capital_gateway.adapter._CONFIRM_DELAY", 0.0)
    mock_session()
    respx.post(f"{API}/positions").mock(
        return_value=httpx.Response(200, json={"dealReference": "ref-late"})
    )
    confirms = respx.get(url__startswith=f"{API}/confirms/").mock(
        return_value=httpx.Response(404, json={})
    )

    order = await adapter.place_order(
        PlaceOrderRequest(symbol="GOLD", direction=Direction.BUY, size=0.01)
    )

    # The reference is the whole value of this answer: it is what lets a caller find out
    # later whether it holds a position.
    assert order.status is OrderStatus.PENDING
    assert order.reference == "ref-late"
    assert confirms.call_count == 5
    await adapter.aclose()


@respx.mock
async def test_cancelling_a_working_order_settles_as_cancelled(adapter: CapitalAdapter) -> None:
    mock_session()
    respx.delete(f"{API}/workingorders/wo-1").mock(
        return_value=httpx.Response(200, json=load_fixture("wo_cancel.json"))
    )
    respx.get(url__startswith=f"{API}/confirms/").mock(
        return_value=httpx.Response(200, json=load_fixture("wo_cancel_confirm.json"))
    )

    order = await adapter.cancel_working_order("wo-1")

    assert order.status is OrderStatus.CANCELLED
    await adapter.aclose()


@respx.mock
async def test_closing_a_position_settles_as_closed(adapter: CapitalAdapter) -> None:
    mock_session()
    respx.delete(f"{API}/positions/deal-1").mock(
        return_value=httpx.Response(200, json=load_fixture("close_position.json"))
    )
    respx.get(url__startswith=f"{API}/confirms/").mock(
        return_value=httpx.Response(200, json=load_fixture("confirm_close.json"))
    )

    order = await adapter.close_position("deal-1")

    assert order.status is OrderStatus.CLOSED
    await adapter.aclose()
