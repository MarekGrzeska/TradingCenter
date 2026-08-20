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
from ._shared import READ_ONLY, WRITE, _read, _send_change


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


class AccountOut(BaseModel):
    id: str
    name: str
    currency: str
    balance: float
    available: float
    active: bool


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

    @mcp.tool(annotations=READ_ONLY)
    async def list_accounts() -> list[AccountOut]:
        """Every demo account these credentials reach, with the one currently active
        marked. Use it before `switch_active_account` to find an id, and to see where the
        money that `get_balance` reports actually sits."""
        rows = await _read(gateway, "/accounts")
        return [
            AccountOut(
                id=row["id"],
                name=row["name"],
                currency=row["currency"],
                balance=row["balance"],
                available=row["available"],
                active=bool(row.get("active")),
            )
            for row in rows
        ]

    @mcp.tool(annotations=WRITE)
    async def switch_active_account(account_id: str) -> AccountOut:
        """Make another demo account the one that orders and positions act on. Take the id
        from `list_accounts`.

        Switching drops the provider's quote stream: the archive that collects candles
        loses its feed for a few seconds and reconnects on its own. That gap is in the
        collected data, not in this conversation, so nothing here will show it to you —
        do not switch accounts in the middle of asking about a live market.
        """
        payload = await _send_change(
            gateway,
            "PUT",
            "/accounts/active",
            json={"account_id": account_id},
            read_back="read the accounts",
        )
        return AccountOut(
            id=payload["id"],
            name=payload["name"],
            currency=payload["currency"],
            balance=payload["balance"],
            available=payload["available"],
            active=True,
        )

    @mcp.tool(annotations=WRITE)
    async def top_up_demo_account(amount: float) -> AccountOut:
        """Move the active demo account's balance by `amount`, and answer with the account
        as it stands afterwards. Negative takes funds away, which is as much a way of
        setting up a test as adding them.

        Demo money only — this module never reaches a live account. The provider keeps its
        own limits on how much a balance may hold, how large one adjustment may be, and how
        many may be made in a day; when one of them stops this, the refusal says which.
        """
        payload = await _send_change(
            gateway,
            "POST",
            "/accounts/top-up",
            json={"amount": amount},
            read_back="read the accounts",
        )
        return AccountOut(
            id=payload["id"],
            name=payload["name"],
            currency=payload["currency"],
            balance=payload["balance"],
            available=payload["available"],
            active=bool(payload.get("active", True)),
        )
