"""The registry, and the check that a strategy's facts are ones the archive announces."""

from __future__ import annotations

import pytest

from strategy.catalogue import all_entries, check_facts_are_announced, get
from strategy.errors import UnknownFactIndicator, UnknownStrategy


def test_the_catalogue_carries_the_strategy_of_reference() -> None:
    """First on purpose: the floor every later strategy is measured against, and the test
    of whether the contract is honest enough to carry a trivial entry unchanged."""
    assert any(spec.id == "baseline_ma_cross" for spec in all_entries())


def test_an_unknown_id_is_refused_by_name() -> None:
    with pytest.raises(UnknownStrategy, match="no_such_strategy"):
        get("no_such_strategy")


def test_every_entry_resolves_its_own_defaults() -> None:
    """A default outside its range is caught at import; this is the other half — that the
    references a fact makes can actually be substituted from the entry's own parameters."""
    for spec in all_entries():
        params = spec.resolve_params()
        for fact in spec.facts:
            assert set(fact.resolved_params(params)) == set(fact.params)


class TestFactsAreAnnounced:
    def test_a_strategy_whose_indicators_are_all_announced_passes(self) -> None:
        spec = get("baseline_ma_cross")
        check_facts_are_announced(spec, {"ema", "atr", "rsi"})

    def test_an_indicator_the_archive_does_not_announce_is_refused_by_name(self) -> None:
        """Named, because the indicator is the only part anybody can act on: the answer is
        either a spelling fix here or an entry the archive has to grow."""
        spec = get("baseline_ma_cross")
        with pytest.raises(UnknownFactIndicator) as refused:
            check_facts_are_announced(spec, {"ema"})
        assert refused.value.indicator == "atr"
        assert "atr" in str(refused.value)
