"""Reading the account: positions, resting orders, balance. No price, candle or
indicator tool lives here — that is market-mcp's archive, named explicitly in every
description below rather than left for a model to guess
(specs/trading-mcp-tools, "Zestaw obejmuje rachunek i wykonanie, a nie rynek").
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel

from ..client import GatewayClient
from ..errors import ToolRefusal
from ._shared import READ_ONLY, _read


class PositionOut(BaseModel):
    id: str
    symbol: str
    direction: str
    size: float
    open_level: float | None = None
    pnl: float | None = None
    currency: str | None = None


class WorkingOrderOut(BaseModel):
    id: str
    symbol: str
    direction: str
    size: float
    order_type: str
    level: float | None = None
    good_till: str | None = None
    currency: str | None = None


class BalanceOut(BaseModel):
    account_id: str
    name: str
    currency: str
    balance: float
    available: float
    pnl: float


def register(mcp: FastMCP, gateway: GatewayClient) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def get_positions() -> list[PositionOut]:
        """Open positions on the demo account — no price here, only what was already
        opened and its running result. An account with nothing open answers an empty
        list, not an error.
        """
        rows = await _read(gateway, "/positions")
        return [PositionOut.model_validate(row) for row in rows]

    @mcp.tool(annotations=READ_ONLY)
    async def get_working_orders() -> list[WorkingOrderOut]:
        """Resting LIMIT and STOP orders on the demo account that have not filled
        yet."""
        rows = await _read(gateway, "/working-orders")
        return [WorkingOrderOut.model_validate(row) for row in rows]

    @mcp.tool(annotations=READ_ONLY)
    async def get_balance() -> BalanceOut:
        """The demo account's balance, available funds and running profit or loss.
        Not a price and not a position — call `get_positions` for what is open."""
        rows = await _read(gateway, "/accounts")
        for row in rows:
            if row.get("active"):
                return BalanceOut(
                    account_id=row["id"],
                    name=row["name"],
                    currency=row["currency"],
                    balance=row["balance"],
                    available=row["available"],
                    pnl=row["pnl"],
                )
        raise ToolRefusal("refused: capital-gateway did not name an active account")
