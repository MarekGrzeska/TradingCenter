"""The catalogue: every strategy this image carries, assembled in one place.

The list below is the only file that changes when a strategy is added. Nothing in
`runner/`, `routers/`, `tools/` or `archive.py` may import an entry module directly —
`tests/test_layering.py` refuses it — so the runtime knows the catalogue and never a
strategy, which is what "adding one changes no file of the runtime" means in practice.

The entries are code in the image rather than rows in a table, and that is a decision with
a cost: a new strategy is a deployment. What it buys is the property the whole platform
stands on — `evaluate` is an ordinary reviewed function, unit-testable and identical in the
loop and in the backtest. A strategy expressed as data would need an interpreter, and the
interpreter would be code to deploy anyway (design.md, decision 1).
"""

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
    """Refuse a strategy whose facts name an indicator the archive does not announce.

    Called when a strategy is registered into the running platform — when a watch is
    created — rather than at import: what the archive announces is not knowable from here
    without asking it, and asking it at import would make this module's start depend on
    another module's health.

    The refusal names the indicator, because that is the only part anybody can act on
    (`strategy-runtime`, "Fakty pochodzą z archiwum, jedną drogą").
    """
    known = set(announced)
    for indicator in spec.indicators:
        if indicator not in known:
            raise UnknownFactIndicator(spec.id, indicator)
