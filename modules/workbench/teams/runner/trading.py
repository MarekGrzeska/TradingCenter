"""The trading ceilings, and the one place a run is stopped for orders rather than for
money or for work.

A deliberate twin of `cost.py`, with the same two moments and the same reasoning: the
**per-run** count is checked before every write call, because that is the last moment at
which not placing an order is still possible; the **daily** count is checked before a run
starts (`routers/runs.py`), because a run refused halfway is a run that already traded.

**Where this twin diverges, and it is the point of `teams-trading`:** every limit here is
optional and an absent one means no limit at all. There is no default, and there is no
number in this file an operator cannot raise — a team let loose on the whole account is an
experiment they are entitled to run, and refusing to run it would be this module making
that decision for them (specs/teams-trading, "Każda granica handlowa daje się wyłączyć, a
moduł żadnej nie narzuca").

What is *not* theirs to move lives in `trading-mcp`, which refuses to start against
anything but the demo account. That is the split worth keeping in mind before adding any
ceiling to this module: **a number the operator cannot change belongs over there, not
here.**
"""

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
    """How many orders this run has placed, and whether it may place another.

    Counted in memory rather than re-read before every call, and for the same reason
    `CostGuard` gives: rows land as calls resolve, several agents write at once, and a
    guard reading a count mid-write would let a call through against a number already
    stale. The run is one process (`engine.py`), so the accumulator is the count.

    An order is counted when it is **sent**, not when it comes back. An order whose reply
    never arrived may well have reached the account, and a ceiling that forgave it would
    be one an outage could walk through.
    """

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
        """Raises before a write call is made, or returns.

        Two different refusals on purpose, and the difference is whether the agent can do
        anything about it (specs/teams-trading, "Granica jest sprawdzana przed wywołaniem
        narzędzia zapisującego"):

        - `RunOrderLimitReached` stops the run. Nothing the model does next changes the
          count, so letting it keep working would burn tokens on a team that can no
          longer act;
        - `OrderTooLarge` comes back to the model as a refused call and the run goes on.
          A size is something an agent can correct, and refusing the call says exactly
          what to correct it to.
        """
        if self._per_run is not None and self._placed >= self._per_run:
            raise RunOrderLimitReached(self._placed, self._per_run)

        if self._max_size is None:
            return
        size = _decimal_or_none(arguments.get("size"))
        if size is not None and size > self._max_size:
            raise OrderTooLarge(size, self._max_size)


def _decimal_or_none(value: Any) -> Decimal | None:
    """Whatever the model or the definition put there, as a number — or `None` when it is
    not one. A `size` this cannot read is not treated as zero and not treated as
    enormous: the size limit simply has nothing to compare, and the call goes to
    `trading-mcp`, which is the module that owns what a valid argument looks like."""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
