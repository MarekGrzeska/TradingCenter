"""The strategy of reference, on readings put there by hand: every test is "given these three readings, what did it
decide". The readings are built in `builders.py`, so what a test changes is the one number it is about."""

from __future__ import annotations

import pytest

from strategy.catalogue import get

from .builders import crossing_facts

SPEC = get("baseline_ma_cross")
PARAMS = SPEC.resolve_params()


def decide(**kwargs):
    return SPEC.evaluate(crossing_facts(**kwargs), PARAMS)


class TestTheCrossing:
    def test_a_crossing_on_this_bar_is_a_trade(self) -> None:
        decision = decide(fast=[99.0, 101.0], slow=[100.0, 100.0], closes=(100.0, 101.0))

        assert decision.action == "trade"
        assert decision.direction == "long"
        assert decision.reason == "the fast average crossed above the slow one"

    def test_a_fast_average_already_above_is_not_a_crossing(self) -> None:
        """The commonest refusal, and the one that keeps the strategy from entering every
        bar of a trend it is already in."""
        decision = decide(fast=[101.0, 102.0], slow=[100.0, 100.0])

        assert decision.action == "no_trade"
        assert "did not cross" in (decision.reason or "")

    def test_a_crossing_the_other_way_is_not_a_trade(self) -> None:
        decision = decide(fast=[101.0, 99.0], slow=[100.0, 100.0])

        assert decision.action == "no_trade"

    def test_touching_without_crossing_is_not_a_crossing(self) -> None:
        """Equal is not above. Written down because `>=` here would enter on every bar of a
        flat market where the two averages sit on each other."""
        decision = decide(fast=[100.0, 100.0], slow=[100.0, 100.0])

        assert decision.action == "no_trade"


class TestTheLevels:
    def test_the_stop_sits_a_multiple_of_range_below_the_close(self) -> None:
        decision = decide(fast=[99.0, 101.0], slow=[100.0, 100.0], atr=[2.0, 2.0], closes=(100.0, 110.0))

        # stop_atr defaults to 2, so 110 - 2*2 = 106.
        assert decision.stop == pytest.approx(106.0)
        assert decision.entry == pytest.approx(110.0)

    def test_the_target_is_the_reward_multiple_of_the_risk(self) -> None:
        decision = decide(fast=[99.0, 101.0], slow=[100.0, 100.0], atr=[2.0, 2.0], closes=(100.0, 110.0))

        # risk is 4, reward_multiple defaults to 3, so 110 + 12.
        assert decision.target == pytest.approx(122.0)
        assert decision.rr == pytest.approx(3.0)

    def test_the_reward_multiple_is_what_reward_over_risk_comes_to(self) -> None:
        """Across the whole parameter range, because the two are the same statement and a
        change to either has to keep them so."""
        for multiple in (1.0, 2.5, 10.0):
            params = SPEC.resolve_params({"reward_multiple": multiple})
            decision = SPEC.evaluate(
                crossing_facts(fast=[99.0, 101.0], slow=[100.0, 100.0], atr=[2.0, 2.0]), params
            )
            assert decision.rr == pytest.approx(multiple)


class TestWhatItRefusesToGuess:
    def test_an_unsettled_average_is_not_a_signal(self) -> None:
        """A line the archive could not fill over the range read. Not an error and not a
        crossing — simply not enough to say anything."""
        decision = decide(fast=[None, 101.0], slow=[100.0, 100.0])

        assert decision.action == "no_trade"
        assert "settled" in (decision.reason or "")

    def test_a_fact_the_archive_could_not_compute_is_named(self) -> None:
        from strategy.catalogue.baseline import FAST, RANGE, SLOW
        from strategy.spec import FactValue

        from .builders import facts, line

        broken = FactValue(key=RANGE, resolution="HOUR", error="no minute series for US100")
        decision = SPEC.evaluate(
            facts(
                values={
                    FAST: line(FAST, "ema", [99.0, 101.0]),
                    SLOW: line(SLOW, "ema", [100.0, 100.0]),
                    RANGE: broken,
                }
            ),
            PARAMS,
        )

        assert decision.action == "no_trade"
        assert "no minute series" in (decision.reason or "")

    def test_a_missing_fact_is_not_read_as_a_reading(self) -> None:
        from strategy.catalogue.baseline import FAST, SLOW

        from .builders import facts, line

        decision = SPEC.evaluate(
            facts(values={FAST: line(FAST, "ema", [99.0, 101.0]), SLOW: line(SLOW, "ema", [100.0, 100.0])}),
            PARAMS,
        )

        assert decision.action == "no_trade"
        assert "was not read" in (decision.reason or "")

    def test_a_zero_range_has_nothing_to_size_a_stop_by(self) -> None:
        decision = decide(fast=[99.0, 101.0], slow=[100.0, 100.0], atr=[0.0, 0.0])

        assert decision.action == "no_trade"
        assert "nothing to size a stop by" in (decision.reason or "")


class TestItIsAFunction:
    def test_the_same_readings_decide_the_same_way(self) -> None:
        """The property everything downstream stands on: replay of a recorded decision, and
        the backtest calling the very function the loop calls."""
        given = crossing_facts(fast=[99.0, 101.0], slow=[100.0, 100.0])

        assert SPEC.evaluate(given, PARAMS) == SPEC.evaluate(given, PARAMS)

    def test_a_refusal_still_reports_what_it_measured(self) -> None:
        """The features are what a report attributes an edge to, so they are worth having
        on the bars where nothing happened as well as on the ones where something did."""
        decision = decide(fast=[101.0, 102.0], slow=[100.0, 100.0], atr=[2.0, 2.0])

        assert decision.features["separation_atr"] == pytest.approx(1.0)
