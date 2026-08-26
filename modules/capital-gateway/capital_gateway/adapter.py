"""CapitalAdapter — raw capital.com payloads in, neutral DTOs out. Hides every provider
quirk: the session, the navigation tree, the async ``dealReference -> confirms`` settlement."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import httpx

from . import history, mapping
from .client import CapitalClient
from .config import environment_of
from .dtos import (
    Account,
    AssetClass,
    Candle,
    CandleHistory,
    Capabilities,
    Instrument,
    InstrumentPage,
    InstrumentTerms,
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

# Reused so a caller reading a period boundary does not ask `GET /markets/{epic}` twice against
# a 10 req/s budget counted per account. Bounded by its error: a stale `forming` undoes itself.
_MARKET_STATUS_MEMO_SECONDS = 5.0


class CapitalAdapter:
    def __init__(self, client: CapitalClient) -> None:
        self._c = client
        self._market_open_memo: dict[str, tuple[float, bool]] = {}

    async def aclose(self) -> None:
        await self._c.aclose()

    @staticmethod
    def _json_ok(resp: httpx.Response) -> dict:
        """Parse a read, or raise on a non-2xx — so a rate-limit or error payload never
        reaches a mapper and surfaces as a KeyError about a field nobody asked for."""
        if not resp.is_success:
            raise GatewayError(f"capital.com {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    @staticmethod
    def _write_json(resp: httpx.Response) -> dict:
        """Deliberately not `_json_ok`: the provider's JSON refusal of an order is an answer
        about the order, while a body that is not JSON at all used to surface as a 500."""
        try:
            return resp.json()
        except ValueError as err:
            raise GatewayError(
                f"capital.com answered {resp.status_code} with a body that is not JSON: "
                f"{resp.text[:200]!r}"
            ) from err

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

    async def top_up(self, amount: float) -> Account:
        """Moves the demo balance and answers with the account as it stands afterwards. The
        provider's own limits are not copied here; a refusal carries its reason (design.md, D3)."""
        r = await self._c.top_up(amount)
        if not r.is_success:
            raise GatewayError(
                f"capital.com refused the balance adjustment: {r.text[:200]}",
                status_code=400 if r.status_code < 500 else 502,
            )
        data = self._json_ok(await self._c.accounts())
        active = await self._active_account_id()
        for acc in data.get("accounts", []):
            if acc.get("accountId") == active:
                return mapping.account_from_raw(acc, active=True)
        raise GatewayError("capital.com did not name an active account after the top-up")

    async def search_instruments(self, query: str) -> list[Instrument]:
        data = self._json_ok(await self._c.search_markets(query))
        return [mapping.instrument_from_market(m) for m in data.get("markets", [])]

    async def list_instruments(
        self, max_nodes: int = 300, asset_class: AssetClass | None = None
    ) -> InstrumentPage:
        """``max_nodes`` bounds the walk and ``truncated`` stops a partial catalogue reading as
        complete. ``asset_class`` sieves markets, not branches: a node's name promises no class."""
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
            # Subscripted, not `.get`: the epic is the instrument's identity, so a market
            # without one is a payload nobody can read, not a key to dedupe under.
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

    async def get_instrument_terms(self, symbol: str) -> InstrumentTerms:
        """The deposit and size rules the provider applies to one instrument — the rest of the
        `GET /markets/{epic}` answer `_market_open` already asks for, and used to discard."""
        resp = await self._c.market(symbol)
        if resp.status_code == 404:
            raise GatewayError(f"unknown instrument {symbol!r}", status_code=404)
        return mapping.instrument_terms_from_details(symbol, self._json_ok(resp))

    async def _market_open(self, symbol: str) -> bool:
        """Only the provider knows where a daily period ends, so this stands in for a boundary
        this module refuses to compute. Memoised; a 404 is not, being a refusal the caller needs."""
        now = asyncio.get_running_loop().time()
        remembered = self._market_open_memo.get(symbol)
        if remembered is not None and now - remembered[0] < _MARKET_STATUS_MEMO_SECONDS:
            return remembered[1]

        resp = await self._c.market(symbol)
        if resp.status_code == 404:
            raise GatewayError(f"unknown instrument {symbol!r}", status_code=404)
        snapshot = self._json_ok(resp).get("snapshot") or {}
        is_open = snapshot.get("marketStatus") == "TRADEABLE"
        self._market_open_memo[symbol] = (now, is_open)
        return is_open

    async def get_candles(self, symbol: str, resolution: Resolution, limit: int) -> list[Candle]:
        resp = await self._c.prices(symbol, resolution.value, limit)
        if resp.status_code == 404:
            raise GatewayError(f"unknown instrument {symbol!r}", status_code=404)
        data = self._json_ok(resp)
        candles = [mapping.candle_from_price(p, resolution) for p in data.get("prices", [])]
        return await history.mark_forming(
            candles, resolution, datetime.now(UTC), lambda: self._market_open(symbol)
        )

    async def get_history(
        self,
        symbol: str,
        resolution: Resolution,
        bars: int,
        still_wanted: Callable[[], Awaitable[bool]] | None = None,
        anchor: datetime | None = None,
        floor: datetime | None = None,
    ) -> CandleHistory:
        """The paging rules live in ``history``; this supplies one page fetch and reads what the
        provider's refusals mean. ``anchor`` shapes the first page, ``floor`` bounds the far end."""

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
                # Checked before the status: the bottom of history arrives as a 404 too, and
                # reading it as an unknown symbol would discard every page of a deep read.
                if payload.get("errorCode") == history.HISTORY_EXHAUSTED:
                    return None
                if resp.status_code == 404:
                    raise GatewayError(f"unknown instrument {symbol!r}", status_code=404)
                raise GatewayError(f"capital.com {resp.status_code}: {resp.text[:200]}")
            return [mapping.candle_from_price(p, resolution) for p in resp.json().get("prices", [])]

        page = await history.collect(
            symbol, resolution, bars, fetch_page, still_wanted, anchor, floor
        )
        marked = await history.mark_forming(
            page.candles, resolution, datetime.now(UTC), lambda: self._market_open(symbol)
        )
        return page.model_copy(update={"candles": marked})

    async def list_positions(self) -> list[Position]:
        data = self._json_ok(await self._c.positions())
        return [mapping.position_from_raw(row) for row in data.get("positions", [])]

    async def place_order(self, req: PlaceOrderRequest) -> Order:
        """MARKET opens a position now; LIMIT and STOP rest as working orders. Two provider
        endpoints behind one request shape — the reason this module has an order type."""
        body: dict = {"epic": req.symbol, "direction": req.direction.value, "size": req.size}
        if req.stop_loss is not None:
            body["stopLevel"] = req.stop_loss
        if req.take_profit is not None:
            body["profitLevel"] = req.take_profit

        if req.order_type == OrderType.MARKET:
            body.update(req.provider_params or {})
            created = self._write_json(await self._c.create_position(body))
            return await self._settle(created, accepted=OrderStatus.FILLED)

        body["type"] = req.order_type.value
        body["level"] = req.level
        if req.good_till is not None:
            body["goodTillDate"] = req.good_till
        body.update(req.provider_params or {})
        created = self._write_json(await self._c.create_working_order(body))
        return await self._settle(created, accepted=OrderStatus.WORKING)

    async def close_position(self, position_id: str) -> Order:
        closed = self._write_json(await self._c.close_position(position_id))
        return await self._settle(closed, accepted=OrderStatus.CLOSED)

    async def update_position(self, position_id: str, req: UpdatePositionRequest) -> Order:
        """Set or remove stops. Only the fields the caller named are sent: sending the whole
        model would clear a live stop the caller never mentioned."""
        body: dict = {}
        if "stop_loss" in req.model_fields_set:
            body["stopLevel"] = req.stop_loss
        if "take_profit" in req.model_fields_set:
            body["profitLevel"] = req.take_profit
        updated = self._write_json(await self._c.update_position(position_id, body))
        return await self._settle(updated, accepted=OrderStatus.UPDATED)

    async def list_working_orders(self) -> list[WorkingOrder]:
        data = self._json_ok(await self._c.working_orders())
        return [mapping.working_order_from_raw(row) for row in data.get("workingOrders", [])]

    async def cancel_working_order(self, order_id: str) -> Order:
        cancelled = self._write_json(await self._c.delete_working_order(order_id))
        return await self._settle(cancelled, accepted=OrderStatus.CANCELLED)

    async def _settle(self, created: dict, accepted: OrderStatus = OrderStatus.FILLED) -> Order:
        """capital.com acknowledges a write with a ``dealReference`` and settles it separately,
        so it is polled. Running out gives PENDING: FILLED would claim a position that may not exist."""
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

    def capabilities(self) -> Capabilities:
        """`environment` is derived rather than declared: `trading-mcp` refuses to open a port
        until it has read it, and a constant would answer a question it never asked."""
        return Capabilities(
            provider="capital.com",
            environment=environment_of(self._c.base_url),
            has_positions=True,
            has_streaming=True,
            has_working_orders=True,
            order_types=["MARKET", "LIMIT", "STOP"],
        )
