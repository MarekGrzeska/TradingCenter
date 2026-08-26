"""The trading ceilings, and the one place a run is stopped for orders rather than for money. Every limit here is
optional; what is not the operator's to move lives in `trading-mcp`, which refuses anything but the demo account."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from ..contract import TradingLimits


class TradeLimitReached(RuntimeError):
    """A trading ceiling from the revision stopped something. Named, always, with the
    number that stopped it."""


class RunOrderLimitReached(TradeLimitReached):
    def __init__(self, placed: int, limit: int) -> None:
        super().__init__(
            f"the run's order limit was reached: {placed} of {limit} allowed placed. The "
            "next order was not sent."
        )
        self.placed = placed
        self.limit = limit


class DailyOrderLimitReached(TradeLimitReached):
    def __init__(self, placed: int, limit: int) -> None:
        super().__init__(
            f"this team's daily order limit is used up: {placed} of {limit} allowed placed "
            "today. No run was started."
        )
        self.placed = placed
        self.limit = limit


class OrderTooLarge(TradeLimitReached):
    """Refused to the model as a call, without stopping the run — see `TradeGuard.check`."""

    def __init__(self, size: Decimal, limit: Decimal) -> None:
        super().__init__(
            f"this order's size {size} is over the limit of {limit} set for this team. "
            "The order was not sent; place a smaller one."
        )
        self.size = size
        self.limit = limit


class TradeGuard:
    """How many orders this run has placed, and whether it may place another, counted in memory for `CostGuard`'s reason.
    An order counts when it is *sent*: one whose reply never arrived may have reached the account."""

    def __init__(self, limits: TradingLimits) -> None:
        self._per_run = limits.orders_per_run
        self._max_size = _decimal_or_none(limits.max_order_size)
        self._placed = 0

    @property
    def placed(self) -> int:
        return self._placed

    def placing(self) -> None:
        """Called once per order actually sent."""
        self._placed += 1

    def check(self, arguments: dict[str, Any]) -> None:
        """Raises before a write call is made, or returns. Two refusals, differing in whether the agent can do anything:
        an exhausted count stops the run, a size too large comes back saying exactly what to correct it to."""
        if self._per_run is not None and self._placed >= self._per_run:
            raise RunOrderLimitReached(self._placed, self._per_run)

        if self._max_size is None:
            return
        size = _decimal_or_none(arguments.get("size"))
        if size is not None and size > self._max_size:
            raise OrderTooLarge(size, self._max_size)


def _decimal_or_none(value: Any) -> Decimal | None:
    """Whatever the model or the definition put there, as a number — or `None` when it is not one. A `size`
    this cannot read is neither zero nor enormous: the limit has nothing to compare, and the call goes on."""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
