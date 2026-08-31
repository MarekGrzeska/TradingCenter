"""The cost ceilings, and the one place a run is stopped for money rather than for work: the run limit before every
model call, the daily one before a run starts. Neither lives in a prompt — a ceiling has to hold when a model does not."""

from __future__ import annotations

from decimal import Decimal


class CostLimitReached(RuntimeError):
    """A ceiling this module was configured with stopped something. Named, always, with the number that
    stopped it — "too expensive" tells an operator nothing about what to change."""


class RunCostLimitReached(CostLimitReached):
    def __init__(self, spent: Decimal, limit: Decimal) -> None:
        super().__init__(
            f"the run's cost limit was reached: {spent} spent of {limit} allowed. The next "
            "model call was not made."
        )
        self.spent = spent
        self.limit = limit


class DailyCostLimitReached(CostLimitReached):
    def __init__(self, spent: Decimal, limit: Decimal) -> None:
        super().__init__(
            f"this team's daily cost limit is used up: {spent} spent today of {limit} "
            "allowed. No run was started."
        )
        self.spent = spent
        self.limit = limit


class CostGuard:
    """What one run has spent, and whether it may spend again. Counted in memory rather than re-read, and not for speed:
    several agents write at once, and a guard reading mid-write acts on a stale number."""

    def __init__(self, limit: Decimal | None) -> None:
        self._limit = limit
        self._spent = Decimal(0)

    @property
    def spent(self) -> Decimal:
        return self._spent

    @property
    def limit(self) -> Decimal | None:
        return self._limit

    def add(self, cost: Decimal | None) -> None:
        if cost is not None:
            self._spent += cost

    def check(self) -> None:
        """Raises if the next call would be made past the ceiling. `>=`, not `>`: at exactly the limit the
        budget is used up, and a call made "because it is not over yet" is a call that puts it over."""
        if self._limit is not None and self._spent >= self._limit:
            raise RunCostLimitReached(self._spent, self._limit)


def limit_from(value: str | None) -> Decimal | None:
    """A limit off the definition. Strings on the wire and in JSONB, `Decimal` here, for the rates' reason:
    floats lose exactly the pennies this ledger exists to get right."""
    return None if value is None else Decimal(value)
