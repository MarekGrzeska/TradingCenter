"""Every name the language knows, in one registry: the validator checks a formula against it, and `GET /language` is
printed from it — so a function the validator accepts is a function the description lists, and the other way round.

The functions of the archive's indicator catalogue are not listed here. They are read from `GET /market/indicators` and
joined to this registry at the moment a document is checked, which is why a new catalogue entry needs no change here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class Type(str, Enum):
    NUMBER = "number"
    CONDITION = "condition"


class Place(str, Enum):
    """Where in a document a formula stands, which decides which names it may use."""

    LET = "let"
    ENTRY = "entry"
    EXIT = "exit"
    LIMIT = "limit"


class Arg(str, Enum):
    NUMBER = "number"
    CONDITION = "condition"
    # A whole number of bars, 1 to MAX_BARS, written as a constant or as a parameter — never a formula, so a window's
    # length is known before a single bar is read.
    WINDOW = "window"


# The furthest back an offset or a window reaches, and so the most warm-up one formula can ask for.
MAX_BARS = 5000

RESOLUTIONS: tuple[str, ...] = ("MINUTE", "MINUTE_5", "MINUTE_15", "MINUTE_30", "HOUR", "HOUR_4", "DAY", "WEEK")

SERIES: dict[str, str] = {
    "open": "the bar's first price (bid)",
    "high": "the bar's highest price (bid)",
    "low": "the bar's lowest price (bid)",
    "close": "the bar's last price (bid)",
    "volume": "the bar's volume as the provider reports it",
}
TIME: dict[str, str] = {
    "hour": "the hour the bar starts, UTC, 0–23",
    "minute": "the minute the bar starts, 0–59",
    "weekday": "the day the bar starts, UTC, MONDAY … SUNDAY",
}
CONSTANTS: dict[str, float] = {
    "MONDAY": 0, "TUESDAY": 1, "WEDNESDAY": 2, "THURSDAY": 3, "FRIDAY": 4, "SATURDAY": 5, "SUNDAY": 6,
    "LONG": 1, "SHORT": -1, "FLAT": 0,
}
# The open position. Only where there is one: the exits.
POSITION: dict[str, str] = {
    "position": "LONG, SHORT or FLAT",
    "entry_price": "the price the open position was entered at",
    "bars_in_trade": "how many decision bars the position has been open",
    "open_r": "the open position's result so far, in R, after costs",
}
# Closed trades. Anywhere but a `let`, which is computed once for the whole range and so cannot know them.
HISTORY: dict[str, str] = {
    "losses_in_row": "how many of the last closed trades in a row were losses",
    "last_trade_r": "the last closed trade's result in R; 0 before the first",
    "trades_today": "how many positions were opened today, UTC",
}


@dataclass(frozen=True)
class Function:
    name: str
    args: tuple[Arg, ...]
    returns: Type
    description: str
    # `min(a, b, c…)`: the last argument kind repeats, at least `len(args)` times.
    variadic: bool = False
    # Only these places; `None` is everywhere.
    places: frozenset[Place] | None = None

    def signature(self) -> str:
        names = [arg.value for arg in self.args]
        return f"{self.name}({', '.join(names)}{', …' if self.variadic else ''}) -> {self.returns.value}"


_N, _C, _W = Arg.NUMBER, Arg.CONDITION, Arg.WINDOW

FUNCTIONS: dict[str, Function] = {
    f.name: f
    for f in (
        Function("highest", (_N, _W), Type.NUMBER, "the highest value of x over the last n bars, this one included"),
        Function("lowest", (_N, _W), Type.NUMBER, "the lowest value of x over the last n bars, this one included"),
        Function("sum", (_N, _W), Type.NUMBER, "the sum of x over the last n bars"),
        Function("average", (_N, _W), Type.NUMBER, "the arithmetic mean of x over the last n bars"),
        Function("crosses_above", (_N, _N), Type.CONDITION, "a was at or below b on the previous bar and is above it now"),
        Function("crosses_below", (_N, _N), Type.CONDITION, "a was at or above b on the previous bar and is below it now"),
        Function("rising", (_N, _W), Type.CONDITION, "x rose on each of the last n bars"),
        Function("falling", (_N, _W), Type.CONDITION, "x fell on each of the last n bars"),
        Function("bars_since", (_C,), Type.NUMBER, "how many bars ago the condition was last true; 0 when it is true now"),
        Function("value_when", (_C, _N), Type.NUMBER, "x on the last bar the condition was true"),
        Function("highest_since", (_C, _N), Type.NUMBER, "the highest x since the condition was last true, that bar included"),
        Function("lowest_since", (_C, _N), Type.NUMBER, "the lowest x since the condition was last true, that bar included"),
        Function("abs", (_N,), Type.NUMBER, "the absolute value"),
        Function("min", (_N, _N), Type.NUMBER, "the smallest of its arguments", variadic=True),
        Function("max", (_N, _N), Type.NUMBER, "the largest of its arguments", variadic=True),
        Function("stale", (_N,), Type.CONDITION, "the last available value of x is older than one period of its resolution"),
        Function(
            "at_entry", (_N,), Type.NUMBER, "x on the bar the open position was entered",
            places=frozenset({Place.EXIT}),
        ),
    )
}

RESERVED: frozenset[str] = frozenset(
    {*SERIES, *TIME, *CONSTANTS, *POSITION, *HISTORY, *FUNCTIONS, *RESOLUTIONS, "p", "True", "False"}
)


@dataclass(frozen=True)
class IndicatorParam:
    name: str
    integer: bool
    default: float
    min: float
    max: float


@dataclass(frozen=True)
class Indicator:
    """One entry of the archive's catalogue, as much of it as a formula needs."""

    id: str
    output: str
    params: tuple[IndicatorParam, ...]
    lines: tuple[str, ...]

    @classmethod
    def from_wire(cls, entry: dict[str, Any]) -> Indicator:
        return cls(
            id=entry["id"],
            output=entry["output"],
            params=tuple(
                IndicatorParam(p["name"], p["type"] == "int", float(p["default"]), float(p["min"]), float(p["max"]))
                for p in entry.get("params", [])
            ),
            lines=tuple(line["key"] for line in entry.get("lines", [])),
        )

    def signature(self) -> str:
        params = ", ".join(f"{p.name}={p.default:g}" for p in self.params)
        lines = "" if len(self.lines) <= 1 else f" .{{{', '.join(self.lines)}}}"
        return f"{self.id}({params}){lines} -> number"


def catalogue_from_wire(answer: dict[str, Any]) -> dict[str, Indicator]:
    """`GET /market/indicators`, keyed by id."""
    return {entry["id"]: Indicator.from_wire(entry) for entry in answer.get("indicators", [])}
