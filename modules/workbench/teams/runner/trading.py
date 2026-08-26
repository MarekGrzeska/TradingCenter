"""The trading ceilings, and the one place a run is stopped for orders rather than for money or for work —
a deliberate twin of `cost.py`, with the same two moments and the same reasoning.

Where the twin diverges is the point: every limit here is optional and an absent one means no limit at all.
What is not the operator's to move lives in `trading-mcp`, which refuses anything but the demo account —
which is the split worth keeping in mind: a number the operator cannot change belongs over there."""

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
    """How many orders this run has placed, and whether it may place another. Counted in memory for
    `CostGuard`'s reason: a guard reading a count mid-write acts on a number already stale.

    An order is counted when it is *sent*, not when it comes back: one whose reply never arrived may well
    have reached the account, and a ceiling that forgave it is one an outage could walk through."""

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
        """Raises before a write call is made, or returns. Two different refusals, and the difference is
        whether the agent can do anything about it: an exhausted count stops the run, while a size too
        large comes back as a refused call saying exactly what to correct it to."""
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
