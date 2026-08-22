"""The contract of an entry — the refusals that keep a strategy from being half-declared."""

from __future__ import annotations

import pytest

from strategy.errors import ParamOutOfRange
from strategy.spec import Decision, Fact, Param, StrategySpec, resolutions_of


def entry(**overrides) -> StrategySpec:
    values = {
        "id": "test",
        "name": "Test",
        "description": "a strategy for testing the contract",
        "resolution": "HOUR",
        "evaluate": lambda facts, params: Decision.no_trade("nothing here"),
    }
    values.update(overrides)
    return StrategySpec(**values)  # type: ignore[arg-type]


class TestParameters:
    def test_defaults_are_filled_in(self) -> None:
        spec = entry(params=(Param("period", "int", 20, 2, 200),))
        assert spec.resolve_params() == {"period": 20}

    def test_a_value_outside_its_range_is_refused(self) -> None:
        spec = entry(params=(Param("period", "int", 20, 2, 200),))
        with pytest.raises(ParamOutOfRange):
            spec.resolve_params({"period": 500})

    def test_an_int_parameter_comes_back_an_int(self) -> None:
        """The archive is handed this number as an indicator's period; 20.0 and 20 are the
        same value to arithmetic and two different cache keys to anything that spells it."""
        spec = entry(params=(Param("period", "int", 20, 2, 200),))
        assert spec.resolve_params({"period": 30.0}) == {"period": 30}
        assert isinstance(spec.resolve_params({"period": 30.0})["period"], int)

    def test_an_undeclared_key_is_ignored_rather_than_refused(self) -> None:
        """A parameter set written for a later version of a strategy should not stop the
        earlier one from answering."""
        spec = entry(params=(Param("period", "int", 20, 2, 200),))
        assert spec.resolve_params({"period": 30, "from_the_future": 1}) == {"period": 30}

    def test_a_default_outside_its_own_range_is_refused_at_import(self) -> None:
        with pytest.raises(ParamOutOfRange):
            entry(params=(Param("period", "int", 500, 2, 200),))

    def test_the_same_parameter_twice_is_refused(self) -> None:
        with pytest.raises(ValueError, match="twice"):
            entry(params=(Param("p", "int", 1, 1, 2), Param("p", "int", 1, 1, 2)))


class TestFacts:
    def test_a_reference_is_substituted_from_the_strategys_parameters(self) -> None:
        fact = Fact(indicator="ema", resolution="HOUR", params={"period": "fast_period"})
        assert fact.resolved_params({"fast_period": 20}) == {"period": 20.0}

    def test_a_number_is_left_alone(self) -> None:
        fact = Fact(indicator="ema", resolution="HOUR", params={"period": 20})
        assert fact.resolved_params({}) == {"period": 20.0}

    def test_a_reference_to_an_undeclared_parameter_is_refused_at_import(self) -> None:
        with pytest.raises(ValueError, match="which it does not declare"):
            entry(
                facts=(Fact(indicator="ema", resolution="HOUR", params={"period": "nope"}),),
                params=(Param("period", "int", 20, 2, 200),),
            )

    def test_two_facts_under_one_key_are_refused(self) -> None:
        with pytest.raises(ValueError, match="two facts under one key"):
            entry(
                facts=(
                    Fact(indicator="ema", resolution="HOUR"),
                    Fact(indicator="ema", resolution="DAY"),
                )
            )

    def test_a_key_lets_one_indicator_be_declared_twice(self) -> None:
        spec = entry(
            facts=(
                Fact(indicator="ema", resolution="HOUR", key="fast"),
                Fact(indicator="ema", resolution="HOUR", key="slow"),
            )
        )
        assert spec.indicators == ("ema",)

    def test_the_resolutions_read_include_the_strategys_own(self) -> None:
        spec = entry(facts=(Fact(indicator="htf_levels_day", resolution="DAY"),))
        assert resolutions_of(spec) == ("HOUR", "DAY")


class TestDecision:
    def test_a_refusal_must_carry_a_reason(self) -> None:
        with pytest.raises(ValueError, match="reason"):
            Decision(action="no_trade")

    def test_a_trade_must_carry_its_levels(self) -> None:
        with pytest.raises(ValueError, match="direction, entry, stop, target"):
            Decision(action="trade")

    def test_reward_over_risk_is_computed_from_the_levels(self) -> None:
        """Computed at the one place that has both numbers. A strategy handing it in could
        hand in a wrong one, and the gate reading it would be gating on arithmetic."""
        decision = Decision.trade(direction="long", entry=100.0, stop=98.0, target=106.0)
        assert decision.rr == 3.0

    def test_a_stop_at_the_entry_is_refused(self) -> None:
        with pytest.raises(ValueError, match="no risk to size against"):
            Decision.trade(direction="long", entry=100.0, stop=100.0, target=106.0)

    def test_a_refused_trade_keeps_its_features_and_drops_its_claim(self) -> None:
        """What the strategy saw is still what it saw; what it proposed is no longer being
        proposed, so the levels go."""
        decision = Decision.trade(
            direction="long", entry=100.0, stop=98.0, target=106.0, features={"a": 1.0}
        )
        refused = decision.refused("the platform said no")

        assert refused.action == "no_trade"
        assert refused.reason == "the platform said no"
        assert refused.features == {"a": 1.0}
        assert (refused.entry, refused.stop, refused.target, refused.rr) == (None,) * 4
