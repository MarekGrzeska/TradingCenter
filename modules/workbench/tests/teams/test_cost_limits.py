"""The two ceilings: what stops a run mid-work, and what stops one from starting."""

from __future__ import annotations

from decimal import Decimal

import pytest

from teams.runner.cost import CostGuard, RunCostLimitReached, limit_from


def test_a_guard_with_no_limit_never_stops_anything() -> None:
    """specs/teams-usage, "Zespół bez ustawionych granic"."""
    guard = CostGuard(None)

    guard.add(Decimal(100))
    guard.check()  # does not raise


def test_a_guard_stops_the_call_that_would_go_past_the_limit() -> None:
    guard = CostGuard(Decimal("0.10"))

    guard.add(Decimal("0.04"))
    guard.check()
    guard.add(Decimal("0.06"))

    with pytest.raises(RunCostLimitReached) as raised:
        guard.check()

    # Exactly at the limit is already used up: a call made "because it is not over yet" is
    # the call that puts it over.
    assert raised.value.spent == Decimal("0.10")
    assert raised.value.limit == Decimal("0.10")
    # The message carries both numbers — "too expensive" tells an operator nothing about
    # what to change.
    assert "0.10" in str(raised.value)


def test_a_call_with_no_reported_cost_adds_nothing() -> None:
    """Unknown usage is not zero usage and it is not free either — it simply cannot be counted, and
    counting it as zero would be the same lie as writing it as zero."""
    guard = CostGuard(Decimal(1))

    guard.add(None)

    assert guard.spent == Decimal(0)
    guard.check()


def test_a_limit_off_the_definition_is_a_decimal_or_nothing() -> None:
    assert limit_from(None) is None
    assert limit_from("0.25") == Decimal("0.25")
