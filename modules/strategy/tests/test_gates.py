"""The rules that bind every strategy, whichever one it is."""

from __future__ import annotations

from datetime import UTC, datetime

from strategy.archive import Gap
from strategy.gates import apply, coverage, reward_over_risk
from strategy.spec import Decision

GAP = Gap(start=datetime(2026, 8, 1, tzinfo=UTC), end=datetime(2026, 8, 2, tzinfo=UTC))


class TestCoverage:
    def test_a_verified_range_passes(self) -> None:
        assert coverage([]) is None

    def test_a_gap_refuses_and_names_the_stretch(self) -> None:
        """Named, because the remedy is a backfill of that stretch — not a change to the
        strategy, which is what a bare "no data" would send somebody looking for."""
        refusal = coverage([GAP])

        assert refusal is not None
        assert refusal.kind == "coverage"
        assert "2026-08-01" in refusal.reason

    def test_more_than_one_gap_is_counted_rather_than_listed(self) -> None:
        refusal = coverage([GAP, GAP, GAP])

        assert refusal is not None
        assert "and 2 more" in refusal.reason


class TestRewardOverRisk:
    def test_a_trade_below_the_floor_is_refused(self) -> None:
        decision = Decision.trade(direction="long", entry=100.0, stop=99.0, target=100.5)

        refusal = reward_over_risk(decision, 1.5)

        assert refusal is not None
        assert refusal.kind == "limit"

    def test_a_trade_at_the_floor_passes(self) -> None:
        decision = Decision.trade(direction="long", entry=100.0, stop=99.0, target=101.5)

        assert reward_over_risk(decision, 1.5) is None

    def test_a_refusal_has_no_reward_to_judge(self) -> None:
        assert reward_over_risk(Decision.no_trade("nothing here"), 1.5) is None


class TestApply:
    def test_a_decision_nothing_bites_comes_back_as_the_strategy_made_it(self) -> None:
        decision = Decision.trade(direction="long", entry=100.0, stop=98.0, target=110.0)

        out, kind = apply(decision, [None, None])

        assert out is decision
        assert kind == "strategy"

    def test_the_first_refusal_is_the_one_carried(self) -> None:
        """A decision carries one reason, and the one worth carrying is the one that would
        have to be answered first."""
        decision = Decision.trade(direction="long", entry=100.0, stop=99.0, target=100.5)

        out, kind = apply(decision, [coverage([GAP]), reward_over_risk(decision, 1.5)])

        assert out.action == "no_trade"
        assert kind == "coverage"

    def test_a_gate_turns_a_trade_into_a_refusal_that_keeps_what_was_measured(self) -> None:
        decision = Decision.trade(
            direction="long", entry=100.0, stop=99.0, target=100.5, features={"seen": 2.0}
        )

        out, _ = apply(decision, [reward_over_risk(decision, 1.5)])

        assert out.action == "no_trade"
        assert out.features == {"seen": 2.0}
        assert out.entry is None
