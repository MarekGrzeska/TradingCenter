"""Smoke tests that trade on the capital.com demo account, behind ``--run-live-trading`` because
they write. Mocks cannot catch a renamed status or a changed dealing rule; a demo fill is simulated."""

from __future__ import annotations

import asyncio
import json
import time

import pytest
import websockets

from capital_gateway.adapter import CapitalAdapter
from capital_gateway.app import stream_tokens_for
from capital_gateway.client import CapitalClient
from capital_gateway.config import Settings
from capital_gateway.dtos import (
    Direction,
    OrderStatus,
    OrderType,
    PlaceOrderRequest,
    UpdatePositionRequest,
)
from capital_gateway.pool import SessionPool

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
    """The smallest size the provider will accept, and the current bid. Read rather than hard-coded:
    a stale copy fails as a rejected order that looks like a bug in this module."""
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
    # FILLED and not PENDING: the deal settled inside the confirm attempts the adapter allows.
    # PENDING here would mean the settlement budget is too tight for the real provider.
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
    """A size no demo balance covers — the harder refusal shape: the provider accepts the request,
    hands back a reference, and only the confirm says it was refused."""
    size, _ = await dealing(adapter)

    order = await adapter.place_order(
        PlaceOrderRequest(symbol=EPIC, direction=Direction.BUY, size=size * 1_000_000)
    )

    assert order.status is OrderStatus.REJECTED
    # `RC_NOT_ENOUGH_MARGIN`, not a bare status. The field is `rejectReason`; reading the
    # `reason` this module used to look for gave every real refusal a null cause.
    assert order.reason, "the provider refused without saying why"
    assert order.reference

    # capital.com assigns a dealId even to a deal it refuses, so an id proves nothing. What
    # matters is that nothing opened: a rejection that left a position behind is the failure.
    positions = await adapter.list_positions()
    assert all(p.id != order.id for p in positions)


async def _preferred_and_another(client: CapitalClient) -> tuple[str, str]:
    r = await client.accounts()
    accounts = r.json()["accounts"]
    preferred = next(a["accountId"] for a in accounts if a.get("preferred"))
    others = [a["accountId"] for a in accounts if a["accountId"] != preferred]
    if not others:
        pytest.skip("these credentials reach one account; nothing to switch to")
    return preferred, others[0]


async def test_a_renewed_session_returns_to_its_own_account(settings: Settings) -> None:
    """Measured 28 October 2026: a fresh login opens on the preferred account. The client must
    put a renewed session back where it stood, or an order after an idle spell lands elsewhere."""
    client = CapitalClient(settings)
    try:
        preferred, other = await _preferred_and_another(client)
        assert (await client.switch_account(other)).is_success

        fresh = CapitalClient(settings)
        await asyncio.sleep(1.1)
        try:
            login = await fresh.login()
            assert login.json().get("currentAccountId") == preferred
        finally:
            await fresh.aclose()

        await asyncio.sleep(1.1)  # the provider takes one login per second per key
        client._cst = "expired"  # the provider answers 401, as it does after ten idle minutes
        session = await client.session_details()

        assert session.json().get("accountId") == other
    finally:
        await client.aclose()


async def test_two_accounts_trade_side_by_side_on_their_own_sessions(settings: Settings) -> None:
    """Measured 28 October 2026 and kept here: an order on one account's session is invisible from
    another's, and neither moves the active account."""
    pool = SessionPool(settings)
    try:
        accounts = await pool.default.list_accounts()
        others = [a.id for a in accounts if not a.active]
        if len(others) < 2:
            pytest.skip("two accounts besides the active one are needed")
        active = next(a.id for a in accounts if a.active)
        x, y = await pool.for_account(others[0]), await pool.for_account(others[1])
        size, _ = await dealing(x)

        order = await x.place_order(
            PlaceOrderRequest(symbol=EPIC, direction=Direction.BUY, size=size)
        )
        assert order.status is OrderStatus.FILLED, f"provider refused: {order.reason}"
        try:
            assert any(p.id == order.id for p in await x.list_positions())
            assert all(p.id != order.id for p in await y.list_positions())
            assert all(p.id != order.id for p in await pool.default.list_positions())
            still_active = [a.id for a in await pool.default.list_accounts() if a.active]
            assert still_active == [active]
        finally:
            await x.close_position(order.id)
    finally:
        await pool.aclose()


async def test_switching_another_session_leaves_the_stream_talking(settings: Settings) -> None:
    """Measured 28 October 2026: a session switching accounts does not break another session's stream."""
    pool = SessionPool(settings)
    try:
        accounts = await pool.default.list_accounts()
        other = next((a.id for a in accounts if not a.active), None)
        if other is None:
            pytest.skip("no second account to switch to")
        cst, token = await stream_tokens_for(pool.stream)
        quotes: list[float] = []
        async with websockets.connect(settings.capital_stream_url) as ws:
            await ws.send(
                json.dumps(
                    {
                        "destination": "marketData.subscribe",
                        "correlationId": "q",
                        "cst": cst,
                        "securityToken": token,
                        "payload": {"epics": [EPIC]},
                    }
                )
            )

            async def listen(seconds: float) -> None:
                deadline = time.monotonic() + seconds
                while (left := deadline - time.monotonic()) > 0:
                    try:
                        message = json.loads(await asyncio.wait_for(ws.recv(), left))
                    except TimeoutError:
                        return
                    if message.get("destination") == "quote":
                        quotes.append(time.monotonic())

            await listen(5)
            before = len(quotes)
            if before == 0:
                pytest.skip(f"{EPIC} is quiet — the market is closed")
            await (await pool.for_account(other)).list_positions()  # a session standing on `other`
            await listen(10)

        if len(quotes) == before:
            await dealing(pool.default)  # skips when the market has just closed
            pytest.fail("the stream went silent after another session switched")
    finally:
        await pool.aclose()
