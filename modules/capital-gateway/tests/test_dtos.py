from __future__ import annotations

import pytest
from pydantic import ValidationError

from capital_gateway.dtos import Direction, OrderType, PlaceOrderRequest, UpdatePositionRequest


def order(**overrides) -> PlaceOrderRequest:
    base = {"symbol": "GOLD", "direction": Direction.BUY, "size": 0.01}
    return PlaceOrderRequest(**{**base, **overrides})


def test_a_market_order_needs_no_level() -> None:
    assert order().level is None


@pytest.mark.parametrize("order_type", [OrderType.LIMIT, OrderType.STOP])
def test_a_resting_order_without_a_level_is_refused(order_type: OrderType) -> None:
    # Refused here, before the provider is contacted — the round trip would only come
    # back as a generic rejection naming nothing.
    with pytest.raises(ValidationError) as err:
        order(order_type=order_type)
    assert "level" in str(err.value)


@pytest.mark.parametrize("order_type", [OrderType.LIMIT, OrderType.STOP])
def test_a_resting_order_with_a_level_is_accepted(order_type: OrderType) -> None:
    assert order(order_type=order_type, level=1900.0).level == 1900.0


def test_a_non_positive_size_is_refused() -> None:
    with pytest.raises(ValidationError):
        order(size=0)


def test_an_amendment_naming_neither_stop_is_refused() -> None:
    with pytest.raises(ValidationError) as err:
        UpdatePositionRequest()
    assert "stop_loss" in str(err.value)


def test_setting_one_stop_leaves_the_other_unset() -> None:
    req = UpdatePositionRequest(stop_loss=1800.0)
    # The tri-state lives in model_fields_set, not in the value: take_profit is None
    # here because it was omitted, and None also means "remove it". Only the set of
    # provided fields tells the two apart.
    assert req.model_fields_set == {"stop_loss"}
    assert req.take_profit is None


def test_clearing_a_stop_is_distinguishable_from_omitting_it() -> None:
    req = UpdatePositionRequest(take_profit=None)
    assert req.model_fields_set == {"take_profit"}
