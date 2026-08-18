"""Changing the account: place, close, amend, cancel.

Every tool here re-checks the demo environment before the gateway is touched — inside
`_write`, which is also where its failures get the same wording as every other failure
in this module (`_shared.py`'s own docstring says why that moved). What is left in this
file is what each tool alone can decide: the arguments that cannot mean anything
together, refused before a request is built rather than after the account has an
opinion about them.

No tool here is retried by this module on its own failure (specs/trading-mcp-execution,
"Moduł nie ponawia zlecenia po własnej awarii").
"""

from __future__ import annotations

from typing import Literal

from mcp.server.fastmcp import FastMCP

from ..client import GatewayClient
from ..errors import ToolRefusal
from ._shared import WRITE, OrderResultOut, _write


def register(mcp: FastMCP, gateway: GatewayClient) -> None:
    @mcp.tool(annotations=WRITE)
    async def place_order(
        symbol: str,
        direction: Literal["BUY", "SELL"],
        size: float,
        order_type: Literal["MARKET", "LIMIT", "STOP"] = "MARKET",
        level: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        good_till: str | None = None,
    ) -> OrderResultOut:
        """Place an order on the demo account. MARKET fills now; LIMIT and STOP rest
        until the market reaches `level`, which both require. `stop_loss` and
        `take_profit` attach on open, at price levels.

        `size` is in the instrument's own units — the ones `get_instrument_terms`
        reports `min_deal_size` and `size_increment` in — never lots and never an amount
        of currency; `size_for_margin` converts a deposit into one. A symbol the provider
        does not know or cannot trade comes back as a refusal naming it, not as a settled
        order. Never retried on this module's own failure — call `get_positions` or
        `get_working_orders` to check the effect of a call that did not come back clean
        before trying again.
        """
        if order_type != "MARKET" and level is None:
            raise ToolRefusal(
                f"refused: {order_type} orders need a target level — provide `level`."
            )
        # The mirror of the line above, and it is the one that costs money if it is
        # missing: `capital-gateway` builds a MARKET order from symbol, direction, size
        # and the two stops, and **silently drops `level` and `good_till`**
        # (`capital_gateway/adapter.py`). An agent that meant "buy, but not above this
        # price" would be filled at whatever the market is, and the `level` it reads back
        # is the fill price — so nothing in the answer reveals its cap was ignored.
        # Refused by name instead, with both ways out of it.
        if order_type == "MARKET":
            ignored = [name for name, value in (("level", level), ("good_till", good_till)) if value is not None]
            if ignored:
                raise ToolRefusal(
                    f"refused: a MARKET order fills at the current price, so "
                    f"{' and '.join(ignored)} would be ignored, not honoured. Drop "
                    f"{'them' if len(ignored) > 1 else 'it'}, or ask for a LIMIT or STOP "
                    "order, which rests until the market reaches `level`."
                )
        body: dict[str, str | float] = {
            "symbol": symbol,
            "direction": direction,
            "size": size,
            "order_type": order_type,
        }
        if level is not None:
            body["level"] = level
        if stop_loss is not None:
            body["stop_loss"] = stop_loss
        if take_profit is not None:
            body["take_profit"] = take_profit
        if good_till is not None:
            body["good_till"] = good_till

        return await _write(gateway, "POST", "/orders", json=body)

    @mcp.tool(annotations=WRITE)
    async def close_position(position_id: str) -> OrderResultOut:
        """Close an open position by id. Read `get_positions` first for the id."""
        return await _write(gateway, "DELETE", f"/positions/{position_id}")

    @mcp.tool(annotations=WRITE)
    async def amend_stops(
        position_id: str,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        clear_stop_loss: bool = False,
        clear_take_profit: bool = False,
    ) -> OrderResultOut:
        """Set or clear an open position's stop-loss and take-profit, independently.
        Both are **price levels**, not distances and not sizes.

        Give `stop_loss`/`take_profit` a number to set it, `clear_stop_loss`/
        `clear_take_profit` to remove it, or say nothing about a stop to leave it exactly
        as it is — an omitted field is unchanged and an explicit removal is different from
        a value, so setting one stop never clears the other.
        """
        if stop_loss is not None and clear_stop_loss:
            raise ToolRefusal("refused: stop_loss and clear_stop_loss cannot both be given")
        if take_profit is not None and clear_take_profit:
            raise ToolRefusal("refused: take_profit and clear_take_profit cannot both be given")
        if stop_loss is None and take_profit is None and not clear_stop_loss and not clear_take_profit:
            raise ToolRefusal(
                "refused: provide stop_loss and/or take_profit to set, or "
                "clear_stop_loss/clear_take_profit to remove — nothing to change"
            )

        body: dict[str, float | None] = {}
        if clear_stop_loss:
            body["stop_loss"] = None
        elif stop_loss is not None:
            body["stop_loss"] = stop_loss
        if clear_take_profit:
            body["take_profit"] = None
        elif take_profit is not None:
            body["take_profit"] = take_profit

        return await _write(gateway, "PUT", f"/positions/{position_id}", json=body)

    @mcp.tool(annotations=WRITE)
    async def cancel_working_order(order_id: str) -> OrderResultOut:
        """Cancel a resting LIMIT or STOP order by id. Read `get_working_orders`
        first for the id."""
        return await _write(gateway, "DELETE", f"/working-orders/{order_id}")
