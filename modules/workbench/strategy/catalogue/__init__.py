"""Every strategy this image carries, and the only file that changes when one is added. Entries are code rather than
rows, so a new strategy is a deployment — what that buys is an `evaluate` identical in the loop and in the backtest."""

from __future__ import annotations

from collections.abc import Iterable

from ..errors import UnknownFactIndicator, UnknownStrategy
from ..spec import StrategySpec
from . import baseline

CATALOGUE: tuple[StrategySpec, ...] = (baseline.moving_average_cross,)

_BY_ID: dict[str, StrategySpec] = {}
for _entry in CATALOGUE:
    if _entry.id in _BY_ID:
        raise ValueError(f"two strategies claim the id {_entry.id!r}")
    _BY_ID[_entry.id] = _entry


def get(strategy_id: str) -> StrategySpec:
    try:
        return _BY_ID[strategy_id]
    except KeyError:
        raise UnknownStrategy(strategy_id) from None


def all_entries() -> tuple[StrategySpec, ...]:
    return CATALOGUE


def check_facts_are_announced(spec: StrategySpec, announced: Iterable[str]) -> None:
    """Refuse a strategy whose facts name an indicator the archive does not announce. Called when a watch
    is created rather than at import: asking at import would make this module's start depend on another's."""
    known = set(announced)
    for indicator in spec.indicators:
        if indicator not in known:
            raise UnknownFactIndicator(spec.id, indicator)
