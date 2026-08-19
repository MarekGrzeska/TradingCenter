from __future__ import annotations

from datetime import UTC, datetime

from market_data.tools.uncertainty import (
    derived_sentence,
    empty_series_sentence,
    uncovered_sentence,
)


def test_no_gaps_is_silent() -> None:
    assert uncovered_sentence([]) is None


def test_gap_names_the_stretch_and_warns_against_reading_it_as_quiet() -> None:
    gap = (datetime(2026, 8, 11, 9, 0, tzinfo=UTC), datetime(2026, 8, 11, 9, 30, tzinfo=UTC))
    sentence = uncovered_sentence([gap])
    assert sentence is not None
    assert "1 stretch" in sentence
    assert "not mean the market was quiet" in sentence


def test_not_derived_is_silent() -> None:
    assert derived_sentence(False, "HOUR") is None


def test_derived_names_the_resolution() -> None:
    sentence = derived_sentence(True, "HOUR")
    assert sentence is not None
    assert "HOUR" in sentence
    assert "not collected from the provider" in sentence


def test_untracked_pair_says_nobody_collects_it() -> None:
    sentence = empty_series_sentence("US100", tracked=False)
    assert "nobody is collecting it" in sentence
    assert "not because the market was quiet" in sentence


def test_tracked_pair_with_no_candle_points_at_coverage() -> None:
    sentence = empty_series_sentence("US100", tracked=True)
    assert "is tracked" in sentence
    assert "describe_coverage" in sentence
