"""The cost ceilings, and the one place a run is stopped for money rather than for work.

Two of them, and they are checked at different moments because they answer different
questions. The **run** limit is checked before every model call, because that is the last
moment at which not spending is still possible (specs/teams-usage, "Moduł MUST sprawdzić
granicę przed wywołaniem modelu"). The **daily** limit is checked before a run starts,
because a run refused halfway is a run that already spent.

Neither lives in a prompt. A prompt is asking a model to restrain itself; a ceiling has to
hold when the model asks for what it should not — and for a team woken by a schedule at
night, this is the only thing between an experiment and a bill nobody approved.
"""

from __future__ import annotations

from decimal import Decimal


class CostLimitReached(RuntimeError):
    """A ceiling this module was configured with stopped something. Named, always, with
    the number that stopped it — "too expensive" tells an operator nothing about what to
    change."""


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
    """What one run has spent so far, and whether it may spend again.

    Counted in memory rather than re-read from the database before every model call, and
    the reason is not speed: rows land as calls finish, several agents write at once, and a
    guard reading a total mid-write would let a call through against a number that was
    already stale. The run is one process (`engine.py`), so the accumulator is the total.

    A row the provider gave no tokens for adds nothing — its cost is unknown, and counting
    an unknown as zero would be the same lie as writing it as zero (specs/teams-usage).
    """

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
        """Raises `RunCostLimitReached` if the next call would be made past the ceiling.

        `>=`, not `>`: at exactly the limit the budget is used up, and a call made "because
        it is not over yet" is a call that puts it over.
        """
        if self._limit is not None and self._spent >= self._limit:
            raise RunCostLimitReached(self._spent, self._limit)


def limit_from(value: str | None) -> Decimal | None:
    """A limit off the definition. Strings on the wire and in JSONB, `Decimal` here — the
    same reason the rates are: a run's budget is compared against sums of small numbers,
    and floats lose exactly the pennies this ledger exists to get right."""
    return None if value is None else Decimal(value)
