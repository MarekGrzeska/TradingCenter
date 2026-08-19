"""The trading ceilings themselves — `runner/trading.py` and the contract they read.

What is proven here is the rule the whole group turns on: a limit is the operator's to
set and the operator's to leave out, and leaving it out means no limit at all
(specs/teams-trading, "Każda granica handlowa daje się wyłączyć, a moduł żadnej nie
narzuca"). The database half — rows written, daily counts — is `test_trading_trace.py`.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from teams.contract import AgentDefinition, TeamDefinition, TradingLimits
from teams.runner.trading import OrderTooLarge, RunOrderLimitReached, TradeGuard

AN_ORDER = {"symbol": "GOLD", "direction": "BUY", "size": 1}


# --- nothing set means nothing enforced ---


def test_a_definition_with_no_trading_limits_is_valid() -> None:
    definition = TeamDefinition(
        agents=[
            AgentDefinition(
                key="trader",
                role="the trader",
                prompt="trade",
                model_id="gpt-5.6-luna",
                tools=["place_order"],
            )
        ]
    )
    assert definition.trading.max_order_size is None
    assert definition.trading.orders_per_run is None
    assert definition.trading.orders_per_day is None


def test_a_guard_with_no_limits_never_stops_anything() -> None:
    """The operator's own call, honoured: a team let loose on the whole account places
    order after order and this module has nothing to say about it. What stops an
    irreversible mistake is the demo account `trading-mcp` refuses to start without."""
    guard = TradeGuard(TradingLimits())

    for _ in range(500):
        guard.check({"symbol": "GOLD", "direction": "BUY", "size": 1_000_000})
        guard.placing()

    assert guard.placed == 500


def test_an_enormous_limit_is_taken_at_face_value() -> None:
    guard = TradeGuard(TradingLimits(max_order_size="99999999", orders_per_run=1_000_000))

    guard.check({"size": "99999998"})  # no raise
    assert guard.placed == 0


# --- each limit works on its own ---


def test_only_the_size_limit_set_leaves_the_counts_unbounded() -> None:
    guard = TradeGuard(TradingLimits(max_order_size="2"))

    for _ in range(50):
        guard.check({"size": "1.5"})
        guard.placing()

    assert guard.placed == 50
    with pytest.raises(OrderTooLarge):
        guard.check({"size": "2.5"})


def test_only_the_run_count_set_leaves_the_size_unbounded() -> None:
    guard = TradeGuard(TradingLimits(orders_per_run=2))

    guard.check({"size": "10000"})
    guard.placing()
    guard.check({"size": "10000"})
    guard.placing()

    with pytest.raises(RunOrderLimitReached):
        guard.check({"size": "1"})


# --- the two refusals are different facts ---


def test_the_run_count_is_reached_at_the_limit_not_past_it() -> None:
    """`>=`, like the cost guard: at exactly the limit the allowance is used up, and an
    order placed "because it is not over yet" is the one that puts it over."""
    guard = TradeGuard(TradingLimits(orders_per_run=1))

    guard.check(AN_ORDER)
    guard.placing()

    with pytest.raises(RunOrderLimitReached) as err:
        guard.check(AN_ORDER)
    assert err.value.placed == 1
    assert err.value.limit == 1
    assert "1 of 1" in str(err.value)


def test_an_oversized_order_names_the_size_and_the_limit() -> None:
    guard = TradeGuard(TradingLimits(max_order_size="0.5"))

    with pytest.raises(OrderTooLarge) as err:
        guard.check({"symbol": "GOLD", "size": "2"})

    assert err.value.size == Decimal(2)
    assert err.value.limit == Decimal("0.5")
    # The agent's next move is a smaller order, so the sentence has to say so.
    assert "smaller" in str(err.value)


def test_an_oversized_order_does_not_count_against_the_run() -> None:
    # The engine only calls `placing()` for orders it actually sends, and this is the
    # property that makes that correct: a refused call must not consume the allowance.
    guard = TradeGuard(TradingLimits(max_order_size="1", orders_per_run=2))

    with pytest.raises(OrderTooLarge):
        guard.check({"size": "5"})

    assert guard.placed == 0


# --- arguments this module cannot read ---


def test_a_size_that_is_not_a_number_is_left_to_the_tool_server() -> None:
    """`trading-mcp` owns what a valid argument looks like. An unreadable size is not
    treated as zero and not treated as enormous — the size limit simply has nothing to
    compare, and the call goes where it will be refused properly."""
    guard = TradeGuard(TradingLimits(max_order_size="1"))

    guard.check({"size": "not a number"})  # no raise
    guard.check({})  # a close_position call carries no size at all


def test_a_call_with_no_size_still_counts_against_the_run() -> None:
    # `close_position` has no size, and it is still an order — the count is of calls that
    # change the account, not of the ones this module could measure.
    guard = TradeGuard(TradingLimits(orders_per_run=1))

    guard.check({"position_id": "p1"})
    guard.placing()

    with pytest.raises(RunOrderLimitReached):
        guard.check({"position_id": "p2"})


# --- what the contract refuses ---


def test_a_zero_count_is_refused_rather_than_read_as_none_allowed() -> None:
    with pytest.raises(ValidationError):
        TradingLimits(orders_per_run=0)


def test_a_negative_size_limit_is_refused() -> None:
    with pytest.raises(ValidationError):
        TradingLimits(max_order_size="-1")


def test_a_size_limit_that_is_not_a_number_is_refused() -> None:
    with pytest.raises(ValidationError, match="not a number"):
        TradingLimits(max_order_size="plenty")
