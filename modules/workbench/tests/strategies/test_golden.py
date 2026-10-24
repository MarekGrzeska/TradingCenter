"""The golden strategies: a change that moves any recorded result must raise `ENGINE_VERSION` (`strategies-backtest`,
"Ten sam wkład daje ten sam wynik"). To re-record after raising it: `uv run python -m tests.strategies.golden.regenerate`."""

from __future__ import annotations

import pytest

from strategies.engine import ENGINE_VERSION

from . import golden


@pytest.fixture(scope="module")
def recording():
    return golden.load()


@pytest.fixture(scope="module")
def data():
    return golden.series()


def test_the_recording_is_of_this_engine_version(recording) -> None:
    assert recording["engine_version"] == ENGINE_VERSION, (
        "ENGINE_VERSION moved without the golden results being re-recorded — run the regenerate script"
    )


@pytest.fixture(scope="module")
def indicators(recording, data):
    return golden.recorded_indicators(recording, data)


@pytest.mark.parametrize("name", sorted(golden.DOCUMENTS))
def test_a_golden_strategy_gives_its_recorded_result(name, recording, data, indicators) -> None:
    difference = golden.same(golden.run(name, data, indicators), recording["cases"][name], name)

    assert difference is None, (
        f"moved under engine version {ENGINE_VERSION} at {difference}: raise ENGINE_VERSION and re-record, or undo it"
    )


def test_the_regenerator_refuses_a_moved_or_vanished_result_and_accepts_an_addition_or_a_new_version() -> None:
    from .golden.regenerate import refusal

    previous = {"engine_version": 3, "cases": {"a": {"x": 1}, "b": {"x": 2}}}

    assert refusal(previous, {"cases": {"a": {"x": 1}, "b": {"x": 9}}}, 3) is not None
    assert refusal(previous, {"cases": {"a": {"x": 1}}}, 3) is not None
    assert refusal(previous, {"cases": {"a": {"x": 1}, "b": {"x": 2}, "c": {"x": 3}}}, 3) is None
    assert refusal(previous, {"cases": {"a": {"x": 7}}}, 4) is None


def test_two_results_within_the_last_bits_are_the_same() -> None:
    assert golden.same({"r": [1.0000001, 2]}, {"r": [1.0, 2]}) is None
    assert golden.same({"r": [1.01]}, {"r": [1.0]}) == ".r[0]: 1.01 vs 1.0"
