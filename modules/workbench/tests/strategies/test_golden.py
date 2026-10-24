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


@pytest.mark.parametrize("name", sorted(golden.DOCUMENTS))
def test_a_golden_strategy_gives_its_recorded_result(name, recording, data) -> None:
    indicators = golden.recorded_indicators(recording, data)

    assert golden.run(name, data, indicators) == recording["cases"][name], (
        f"{name} moved under engine version {ENGINE_VERSION}: raise ENGINE_VERSION and re-record, or undo the change"
    )


def test_the_regenerator_refuses_a_moved_result_under_the_same_version(monkeypatch, tmp_path) -> None:
    import json

    from .golden import regenerate

    moved = golden.load()
    moved["cases"]["state_and_limits"]["trades"] = []
    stale = tmp_path / "golden.json"
    stale.write_text(json.dumps(moved), encoding="utf-8")
    monkeypatch.setattr(regenerate, "RECORDING", stale)
    monkeypatch.setattr(golden, "RECORDING", stale)

    assert regenerate.main() == 1
    assert json.loads(stale.read_text(encoding="utf-8")) == moved
