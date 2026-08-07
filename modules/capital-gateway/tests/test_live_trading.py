"""Smoke tests that trade on the capital.com demo account.

Separate from ``test_live.py`` and behind ``--run-live-trading``, because these write:
they open a position, amend it, close it, rest an order and cancel it. Nothing here is
left behind on purpose — every position is closed in a ``finally`` — but an account that
somebody is watching will show the round trip.

Why they exist at all: the order path was proven only against ``respx``, which proves this
module is consistent with the payloads recorded in July 2026. It cannot catch capital.com
changing a dealing rule, renaming a status, or refusing a shape it used to accept. That is
the entire class of failure a gateway has, and mocks are structurally blind to it.

A demo fill is still a simulated fill. What this proves is the contract — request accepted,
reference settled, status reported — not the execution.
"""

from __future__ import annotations

import pytest

from capital_gateway.adapter import CapitalAdapter
from capital_gateway.client import CapitalClient
from capital_gateway.config import Settings
from capital_gateway.dtos import (
    Direction,
    OrderStatus,
    OrderType,
    PlaceOrderRequest,
    UpdatePositionRequest,
)

pytestmark = pytest.mark.live_trading

EPIC = "US100"


@pytest.fixture
async def adapter(settings: Settings):
    adapter = CapitalAdapter(CapitalClient(settings))
    try:
        yield adapter
    finally:
        await adapter.aclose()


async def dealing(adapter: CapitalAdapter) -> tuple[float, float]:
    """The smallest size the provider will accept, and the current bid.

    Read rather than hard-coded: a minimum deal size is a provider setting, and a test
    carrying last quarter's copy of it fails as a rejected order that looks like a bug in
    this module.
    """
    r = await adapter._c.market(EPIC)
    assert r.is_success, f"cannot read {EPIC}: {r.status_code} {r.text[:200]}"
    market = r.json()
    snapshot = market.get("snapshot") or {}
    if snapshot.get("marketStatus") != "TRADEABLE":
        pytest.skip(f"{EPIC} is {snapshot.get('marketStatus')} — the market is closed")
    size = (market.get("dealingRules") or {}).get("minDealSize", {}).get("value")
    assert size, f"no minDealSize for {EPIC}"
    return float(size), float(snapshot["bid"])


async def test_a_market_order_opens_amends_and_closes_a_position(
    adapter: CapitalAdapter,
) -> None:
    size, bid = await dealing(adapter)

    order = await adapter.place_order(
        PlaceOrderRequest(symbol=EPIC, direction=Direction.BUY, size=size)
    )
    # FILLED and not PENDING: the deal settled inside the confirm attempts the adapter
    # allows. If this ever comes back PENDING the settlement budget is too tight for the
    # real provider, which no mocked confirm can tell us.
    assert order.status is OrderStatus.FILLED, f"provider refused: {order.reason}"
    assert order.id

    try:
        positions = await adapter.list_positions()
        mine = [p for p in positions if p.id == order.id]
        assert mine, f"position {order.id} is not in the account after a FILLED order"
        assert mine[0].symbol == EPIC
        assert mine[0].direction is Direction.BUY

        # Far below a long entry, so the stop cannot be hit while the test runs — the
        # claim is that the amendment reaches the provider, not that a stop works.
        amended = await adapter.update_position(
            order.id, UpdatePositionRequest(stop_loss=round(bid * 0.5, 1))
        )
        assert amended.status is OrderStatus.UPDATED, f"amend refused: {amended.reason}"
    finally:
        closed = await adapter.close_position(order.id)

    assert closed.status is OrderStatus.CLOSED, f"close refused: {closed.reason}"
    remaining = await adapter.list_positions()
    assert all(p.id != order.id for p in remaining)


async def test_a_resting_order_is_listed_and_cancelled(adapter: CapitalAdapter) -> None:
    size, bid = await dealing(adapter)
    # Ten percent under the market: far enough that it rests for the length of the test,
    # near enough that the provider does not refuse the level as unreasonable.
    level = round(bid * 0.9, 1)

    order = await adapter.place_order(
        PlaceOrderRequest(
            symbol=EPIC,
            direction=Direction.BUY,
            size=size,
            order_type=OrderType.LIMIT,
            level=level,
        )
    )
    assert order.status is OrderStatus.WORKING, f"provider refused: {order.reason}"
    assert order.id

    try:
        working = await adapter.list_working_orders()
        mine = [w for w in working if w.id == order.id]
        assert mine, f"working order {order.id} is not listed after a WORKING result"
        assert mine[0].order_type is OrderType.LIMIT
        assert mine[0].level == pytest.approx(level)
    finally:
        cancelled = await adapter.cancel_working_order(order.id)

    assert cancelled.status is OrderStatus.CANCELLED, f"cancel refused: {cancelled.reason}"
    assert all(w.id != order.id for w in await adapter.list_working_orders())


async def test_an_order_the_provider_refuses_comes_back_rejected(
    adapter: CapitalAdapter,
) -> None:
    """A size no demo balance covers.

    There are two shapes of refusal and this is the harder one: the provider *accepts*
    the request, hands back a ``dealReference``, and only the confirm says the deal was
    refused. (The other — an outright error with no reference at all — is covered against
    ``respx``.) So the claim here is that a rejection surviving as far as settlement still
    arrives as REJECTED with a cause, rather than as a fill nobody has.
    """
    size, _ = await dealing(adapter)

    order = await adapter.place_order(
        PlaceOrderRequest(symbol=EPIC, direction=Direction.BUY, size=size * 1_000_000)
    )

    assert order.status is OrderStatus.REJECTED
    # `RC_NOT_ENOUGH_MARGIN`, not a bare status. The field is `rejectReason`; reading the
    # `reason` this module used to look for gave every real refusal a null cause.
    assert order.reason, "the provider refused without saying why"
    assert order.reference

    # capital.com assigns a dealId even to a deal it refuses, so an id here proves
    # nothing. What matters is that nothing opened: a rejection that quietly left a
    # position behind is the failure this test is for.
    positions = await adapter.list_positions()
    assert all(p.id != order.id for p in positions)
