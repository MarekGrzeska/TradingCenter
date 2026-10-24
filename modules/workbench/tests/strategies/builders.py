"""Catalogue entries and scopes as the tests need them: the archive's real wire shape, with only what a test is about."""

from __future__ import annotations

import copy

from strategies.checking import ParamDecl, Scope
from strategies.vocabulary import Indicator, Place, Type, catalogue_from_wire


def _entry(id: str, output: str = "lines", params=(("period", "int", 20, 2, 5000),), lines=None) -> dict:
    return {
        "id": id,
        "output": output,
        "params": [{"name": n, "type": t, "default": d, "min": lo, "max": hi} for n, t, d, lo, hi in params],
        "lines": [{"key": key, "label": key} for key in (lines if lines is not None else [id])],
    }


CATALOGUE_WIRE = {
    "algorithm_version": 1,
    "indicators": [
        _entry("ema"),
        _entry("atr", params=(("period", "int", 14, 1, 5000),)),
        _entry("bbands", params=(("period", "int", 20, 2, 5000), ("mult", "float", 2.0, 0.1, 10.0)),
               lines=["upper", "basis", "lower"]),
        _entry("swing_points", output="markers", params=(("n", "int", 3, 1, 50),), lines=[]),
    ],
}


def catalogue() -> dict[str, Indicator]:
    return catalogue_from_wire(CATALOGUE_WIRE)


def scope(
    place: Place = Place.ENTRY,
    params: dict[str, ParamDecl] | None = None,
    lets: dict[str, Type] | None = None,
) -> Scope:
    return Scope(
        place=place,
        params=params if params is not None else {"fast": ParamDecl(20, 10, 30, 5)},
        lets=lets or {},
        catalogue=catalogue(),
    )


TRACKED = {("US100", "MINUTE"), ("US500", "MINUTE"), ("US500", "DAY")}

_DOCUMENT = {
    "schema": 1,
    "name": "US100 pullback in an H4 trend",
    "hypothesis": "An H1 trend agreeing with H4 continues after a pullback to its EMA.",
    "symbol": "US100",
    "timeframe": "HOUR",
    "params": {"fast": {"default": 20, "min": 10, "max": 30, "step": 5}},
    "let": {
        "fast": "ema(p.fast)",
        "slow": "ema(50)",
        "trend_h4": "ema(20) @ HOUR_4 > ema(50) @ HOUR_4",
        "pullback": "low <= fast and close > fast",
    },
    "entries": [
        {
            "side": "long",
            "when": "trend_h4 and fast > slow and pullback and close @ US500 > ema(200) @ US500 @ DAY",
            "order": {"type": "stop", "price": "high + 0.1 * atr(14)", "expires_bars": 3},
        }
    ],
    "exits": {
        "stop": "entry_price - 2 * at_entry(atr(14))",
        "target": "entry_price + 3 * at_entry(atr(14))",
        "trail": {"after_r": 1.5, "distance": "1.5 * atr(14)"},
        "when": "crosses_below(close, slow)",
        "max_bars": 48,
    },
    "sizing": {"mode": "risk_fraction", "value": 0.005},
    "limits": {"daily_stop_r": -2, "no_entry": "weekday == FRIDAY and hour >= 18"},
}


def document(**changes) -> dict:
    """A document that passes, with top-level sections replaced by `changes`."""
    built = copy.deepcopy(_DOCUMENT)
    built.update(changes)
    return built
