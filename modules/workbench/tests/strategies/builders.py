"""Catalogue entries and scopes as the tests need them: the archive's real wire shape, with only what a test is about."""

from __future__ import annotations

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
