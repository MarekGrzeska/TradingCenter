"""CapitalAdapter — raw capital.com payloads in, neutral DTOs out.

Owns a ``CapitalClient`` and hides every provider quirk: the session, the market
navigation tree, and the asynchronous ``dealReference -> confirms`` settlement. Nothing
above this layer knows what an epic is.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime

import httpx

from . import history, mapping
from .client import CapitalClient
from .dtos import (
    Account,
    AssetClass,
    Candle,
    CandleHistory,
    Capabilities,
    Instrument,
    InstrumentPage,
    Order,
    OrderStatus,
    OrderType,
    PlaceOrderRequest,
    Position,
    Resolution,
    UpdatePositionRequest,
    WorkingOrder,
)
from .errors import GatewayError

_TREE_CONCURRENCY = 5  # parallel marketnavigation requests, under the rate gate
_CONFIRM_ATTEMPTS = 5
_CONFIRM_DELAY = 0.4  # seconds between confirm polls; after the attempts run out -> PENDING


class CapitalAdapter:
    def __init__(self, client: CapitalClient) -> None:
        self._c = client

    async def aclose(self) -> None:
        await self._c.aclose()

    @staticmethod
    def _json_ok(resp: httpx.Response) -> dict:
        """Parse a read, or raise on a non-2xx — so a rate-limit or error payload never
        reaches a mapper and surfaces as a KeyError about a field nobody asked for."""
        if not resp.is_success:
            raise GatewayError(f"capital.com {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    # --- accounts ---

    async def list_accounts(self) -> list[Account]:
        active = await self._active_account_id()
        data = self._json_ok(await self._c.accounts())
        return [
            mapping.account_from_raw(a, active=a.get("accountId") == active)
            for a in data.get("accounts", [])
        ]

    async def _active_account_id(self) -> str | None:
        r = await self._c.session_details()
        return r.json().get("accountId") if r.is_success else None

    async def set_active_account(self, account_id: str) -> Account:
        r = await self._c.switch_account(account_id)
        if not r.is_success:
            raise GatewayError(f"cannot switch to account {account_id}", status_code=400)
        # The switch succeeded, so the target is active now; read the accounts once and
        # mark it, rather than asking the session again for what we just set.
        data = self._json_ok(await self._c.accounts())
        for a in data.get("accounts", []):
            if a.get("accountId") == account_id:
                return mapping.account_from_raw(a, active=True)
        raise GatewayError(f"account {account_id} not found after switch", status_code=404)

    # --- market data ---

    async def search_instruments(self, query: str) -> list[Instrument]:
        data = self._json_ok(await self._c.search_markets(query))
        return [mapping.instrument_from_market(m) for m in data.get("markets", [])]

    async def list_instruments(
        self, max_nodes: int = 300, asset_class: AssetClass | None = None
    ) -> InstrumentPage:
        """Walk the marketnavigation tree, flatten every market, dedupe by symbol.

        ``max_nodes`` is a bound on how much of the tree is visited. asyncio is
        cooperative, so the check and the increment below both run before any await —
        the counter cannot overshoot. The returned ``truncated`` flag is what stops a
        partial catalogue from reading as a complete one.

        ``asset_class`` narrows the result to one class. The sieve is on the markets
        rather than on the branches: a node's name suggests its class but does not
        promise it, and a branch skipped on a guess would drop instruments the caller
        asked for. The walk therefore costs the same either way, which is why the route
        gives a filtered request a larger node budget — one class is a fraction of the
        catalogue, so the same budget reaches much further inside it.
        """
        sem = asyncio.Semaphore(_TREE_CONCURRENCY)
        markets: list[dict] = []
        visited = 0
        truncated = False

        async def visit(node_id: str | None) -> None:
            nonlocal visited, truncated
            if visited >= max_nodes:
                truncated = True
                return
            visited += 1
            async with sem:
                r = await self._c.market_navigation(node_id)
            # A bad node is skipped rather than failing the traversal: one unreadable
            # branch should cost that branch, not the whole catalogue.
            if not r.is_success:
                return
            d = r.json()
            markets.extend(d.get("markets") or [])
            await asyncio.gather(*(visit(s["id"]) for s in d.get("nodes") or []))

        await visit(None)

        seen: set[str] = set()
        out: list[Instrument] = []
        for m in markets:
            # Subscripted, not `.get`: the epic is the instrument's identity and
            # `instrument_from_market` requires it two lines down, so a market without one
            # is a provider payload nobody can read — better said here than deduplicated
            # under a `None` key first.
            epic = m["epic"]
            # The same instrument hangs under several branches, so without this the
            # catalogue reports duplicates as separate instruments.
            if epic in seen:
                continue
            seen.add(epic)
            instrument = mapping.instrument_from_market(m)
            if asset_class is not None and instrument.asset_class != asset_class:
                continue
            out.append(instrument)
        return InstrumentPage(
            instruments=out, count=len(out), truncated=truncated, nodes_visited=visited
        )

    async def get_candles(self, symbol: str, resolution: Resolution, limit: int) -> list[Candle]:
        resp = await self._c.prices(symbol, resolution.value, limit)
        if resp.status_code == 404:
            raise GatewayError(f"unknown instrument {symbol!r}", status_code=404)
        data = self._json_ok(resp)
        return [mapping.candle_from_price(p, resolution) for p in data.get("prices", [])]

    async def get_history(
        self,
        symbol: str,
        resolution: Resolution,
        bars: int,
        still_wanted: Callable[[], Awaitable[bool]] | None = None,
        anchor: datetime | None = None,
        floor: datetime | None = None,
    ) -> CandleHistory:
        """Candles further back than one request reaches.

        The paging rules live in ``history``; this supplies the one page fetch and the
        judgement of what the provider's refusals mean. ``anchor`` shapes only the first
        page — see ``history.collect`` — so a caller can reach for a window that ended
        months ago instead of always reaching back from now. ``floor`` bounds the other
        end: nothing older than it is fetched or returned, which ``bars`` alone cannot
        express for an instrument that is not open around the clock.
        """

        async def fetch_page(
            date_from: str | None, date_to: str | None, limit: int
        ) -> list[Candle] | None:
            resp = await self._c.prices(
                symbol, resolution.value, limit, date_from=date_from, date_to=date_to
            )
            if not resp.is_success:
                try:
                    payload = resp.json()
                except ValueError:
                    payload = {}
                # Checked before the status, because the bottom of history arrives as a
                # 404 too. Reading it as an unknown symbol would raise on the last page
                # of a deep read and throw away every page before it.
                if payload.get("errorCode") == history.HISTORY_EXHAUSTED:
                    return None
                if resp.status_code == 404:
                    raise GatewayError(f"unknown instrument {symbol!r}", status_code=404)
                raise GatewayError(f"capital.com {resp.status_code}: {resp.text[:200]}")
            return [mapping.candle_from_price(p, resolution) for p in resp.json().get("prices", [])]

        return await history.collect(
            symbol, resolution, bars, fetch_page, still_wanted, anchor, floor
        )

    # --- trading ---

    async def list_positions(self) -> list[Position]:
        data = self._json_ok(await self._c.positions())
        return [mapping.position_from_raw(row) for row in data.get("positions", [])]

    async def place_order(self, req: PlaceOrderRequest) -> Order:
        """MARKET opens a position now; LIMIT and STOP rest as working orders.

        Two different provider endpoints, one request shape for the caller — which is
        the whole reason this module has an order type rather than two routes.
        """
        body: dict = {"epic": req.symbol, "direction": req.direction.value, "size": req.size}
        if req.stop_loss is not None:
            body["stopLevel"] = req.stop_loss
        if req.take_profit is not None:
            body["profitLevel"] = req.take_profit

        if req.order_type == OrderType.MARKET:
            body.update(req.provider_params or {})
            created = (await self._c.create_position(body)).json()
            return await self._settle(created, accepted=OrderStatus.FILLED)

        body["type"] = req.order_type.value
        body["level"] = req.level
        if req.good_till is not None:
            body["goodTillDate"] = req.good_till
        body.update(req.provider_params or {})
        created = (await self._c.create_working_order(body)).json()
        return await self._settle(created, accepted=OrderStatus.WORKING)

    async def close_position(self, position_id: str) -> Order:
        closed = (await self._c.close_position(position_id)).json()
        return await self._settle(closed, accepted=OrderStatus.CLOSED)

    async def update_position(self, position_id: str, req: UpdatePositionRequest) -> Order:
        """Set or remove stops. Only the fields the caller named are sent: a value sets,
        None removes, an omitted field is left alone. Sending the whole model would
        clear a live stop the caller never mentioned."""
        body: dict = {}
        if "stop_loss" in req.model_fields_set:
            body["stopLevel"] = req.stop_loss
        if "take_profit" in req.model_fields_set:
            body["profitLevel"] = req.take_profit
        updated = (await self._c.update_position(position_id, body)).json()
        return await self._settle(updated, accepted=OrderStatus.UPDATED)

    async def list_working_orders(self) -> list[WorkingOrder]:
        data = self._json_ok(await self._c.working_orders())
        return [mapping.working_order_from_raw(row) for row in data.get("workingOrders", [])]

    async def cancel_working_order(self, order_id: str) -> Order:
        cancelled = (await self._c.delete_working_order(order_id)).json()
        return await self._settle(cancelled, accepted=OrderStatus.CANCELLED)

    async def _settle(self, created: dict, accepted: OrderStatus = OrderStatus.FILLED) -> Order:
        """Turn the provider's acknowledgement into an outcome.

        capital.com answers a create, close, amend or cancel with a ``dealReference``
        and settles it separately — the acknowledgement says the request was received,
        not that anything happened. So the reference is polled until the deal reports a
        status.

        ``accepted`` is what an ACCEPTED deal means for the action that produced it.

        When the attempts run out the result is PENDING, carrying the reference. That is
        the important case: reporting an unresolved reference as FILLED would tell a
        caller it holds a position that may not exist, and the reference is what lets it
        find out later.
        """
        ref = created.get("dealReference")
        if not ref:
            # No reference at all means the provider refused before the deal existed —
            # the payload carries an error code instead.
            reason = created.get("errorCode") or str(created)
            return Order(status=OrderStatus.REJECTED, reason=reason)
        for _ in range(_CONFIRM_ATTEMPTS):
            r = await self._c.confirm(ref)
            if r.is_success and r.json().get("dealStatus"):
                return mapping.order_from_confirm(r.json(), accepted_status=accepted)
            await asyncio.sleep(_CONFIRM_DELAY)
        return Order(status=OrderStatus.PENDING, reference=ref)

    # --- meta ---

    def capabilities(self) -> Capabilities:
        return Capabilities(
            provider="capital.com",
            environment="demo",
            has_positions=True,
            has_streaming=True,
            has_working_orders=True,
            order_types=["MARKET", "LIMIT", "STOP"],
        )
