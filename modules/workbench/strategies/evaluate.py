"""Formulas turned into values, in two phases (design D4). A formula that reads no trade state is computed for its whole
axis at once on numpy: offsets only look back, windows only trail, and another series is aligned by the moment each of
its bars became known. A formula that reads the trade's state is interpreted one bar at a time while the engine walks,
reading the first phase's columns for every part of it that has no state."""

from __future__ import annotations

import operator
from collections.abc import Callable, Mapping
from dataclasses import dataclass

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from . import formula as f
from . import sessions
from .checking import children, through_at
from .document import Checked
from .requirements import IndicatorKey, indicator_key
from .series import PERIOD_SECONDS, Context, Series, align, pick
from .vocabulary import (
    CONSTANTS,
    FUNCTIONS,
    HISTORY,
    PER_BAR,
    POSITION,
    SESSION_FUNCTIONS,
    SESSIONS,
    Indicator,
)

_COMPARE: dict[str, Callable] = {
    "<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge, "==": operator.eq, "!=": operator.ne,
}
_ARITH: dict[str, Callable] = {"+": np.add, "-": np.subtract, "*": np.multiply, "/": np.divide}


@dataclass
class State:
    """The trade as the engine knows it on one bar."""

    position: int = 0
    entry_price: float = np.nan
    entry_bar: int = -1
    bars_in_trade: int = 0
    open_r: float = np.nan
    losses_in_row: int = 0
    last_trade_r: float = 0.0
    trades_today: int = 0

    def name(self, name: str) -> float:
        return float(getattr(self, name))


class Evaluator:
    def __init__(
        self,
        checked: Checked,
        params: Mapping[str, float],
        catalogue: Mapping[str, Indicator],
        series: Mapping[Context, Series],
        indicators: Mapping[IndicatorKey, np.ndarray],
    ) -> None:
        d = checked.document
        self.decision: Context = (d.symbol, d.timeframe)
        self._lets = {name: checked.formulas[f"let.{name}"] for name in checked.let_order}
        self._params = params
        self._catalogue = catalogue
        self._series = series
        self._indicators = indicators
        self._vectors: dict[tuple[f.Node, Context], np.ndarray] = {}
        self._stateful: dict[f.Node, bool] = {}

    # --- phase one: whole axes -----------------------------------------------------------------------------------

    def vector(self, node: f.Node, ctx: Context | None = None) -> np.ndarray:
        ctx = ctx or self.decision
        key = (node, ctx)
        if key not in self._vectors:
            self._vectors[key] = self._compute(node, ctx)
        return self._vectors[key]

    def _length(self, ctx: Context) -> int:
        return len(self._series[ctx])

    def _compute(self, n: f.Node, ctx: Context) -> np.ndarray:
        size = self._length(ctx)
        if isinstance(n, f.Num):
            return np.full(size, n.value)
        if isinstance(n, f.Bool):
            return np.full(size, n.value)
        if isinstance(n, f.Param):
            return np.full(size, float(self._params[n.name]))
        if isinstance(n, f.Name):
            return self._name(n.id, ctx)
        if isinstance(n, f.Neg):
            return -self.vector(n.operand, ctx)
        if isinstance(n, f.Arith):
            with np.errstate(divide="ignore", invalid="ignore"):
                out = _ARITH[n.op](self.vector(n.left, ctx), self.vector(n.right, ctx))
            return np.where(np.isfinite(out), out, np.nan)
        if isinstance(n, f.Compare):
            values = [self.vector(o, ctx) for o in n.operands]
            out = np.ones(size, dtype=bool)
            for op, left, right in zip(n.ops, values, values[1:], strict=False):
                out &= _COMPARE[op](left, right) & ~np.isnan(left) & ~np.isnan(right)
            return out
        if isinstance(n, f.Logic):
            values = [self.vector(v, ctx) for v in n.values]
            return np.logical_and.reduce(values) if n.op == "and" else np.logical_or.reduce(values)
        if isinstance(n, f.Not):
            return ~self.vector(n.operand, ctx)
        if isinstance(n, f.IfElse):
            return np.where(self.vector(n.condition, ctx), self.vector(n.then, ctx), self.vector(n.otherwise, ctx))
        if isinstance(n, f.Lag):
            return _shift(self.vector(n.value, ctx), self._count(n.bars))
        if isinstance(n, f.At):
            value, inner = through_at(n, ctx)
            index = align(self._series[inner].available, self._series[ctx].available)
            return pick(self.vector(value, inner), index)
        if isinstance(n, f.Field) and isinstance(n.value, f.Call):
            return self._indicator(n.value, n.name, ctx)
        if isinstance(n, f.Call):
            if n.function not in FUNCTIONS:
                return self._indicator(n, None, ctx)
            return self._function(n, ctx)
        raise TypeError(f"no value for {type(n).__name__}")  # the checker lets nothing else through

    def _name(self, name: str, ctx: Context) -> np.ndarray:
        series = self._series[ctx]
        if name in series.columns:
            return series.columns[name]
        if name == "hour":
            return ((series.starts // 3600) % 24).astype(np.float64)
        if name == "minute":
            return ((series.starts // 60) % 60).astype(np.float64)
        if name == "weekday":
            return (((series.starts // 86400) + 3) % 7).astype(np.float64)  # 1970-01-01 was a Thursday
        if name in CONSTANTS:
            return np.full(len(series), float(CONSTANTS[name]))
        if name in self._lets:
            return self.vector(self._lets[name], self.decision)
        raise KeyError(f"`{name}` has no value on a whole axis")

    def _indicator(self, call: f.Call, line: str | None, ctx: Context) -> np.ndarray:
        return self._indicators[indicator_key(call, line, ctx, self._catalogue, self._params)]

    def _count(self, bars: int | f.Param) -> int:
        return bars if isinstance(bars, int) else int(self._params[bars.name])

    def _function(self, n: f.Call, ctx: Context) -> np.ndarray:
        name, args = n.function, n.args

        def v(i: int) -> np.ndarray:
            return self.vector(args[i], ctx)

        def window(i: int) -> int:
            arg = args[i]
            return int(arg.value) if isinstance(arg, f.Num) else int(self._params[arg.name])  # type: ignore[union-attr]

        if name in ("highest", "lowest", "sum", "average"):
            reducer = {"highest": np.max, "lowest": np.min, "sum": np.sum, "average": np.mean}[name]
            return _rolling(v(0), window(1), reducer)
        if name in ("crosses_above", "crosses_below"):
            a, b = v(0), v(1)
            before, now = (_shift(a, 1) <= _shift(b, 1), a > b) if name == "crosses_above" else (
                _shift(a, 1) >= _shift(b, 1), a < b)
            return before & now & ~np.isnan(_shift(a, 1)) & ~np.isnan(_shift(b, 1)) & ~np.isnan(a) & ~np.isnan(b)
        if name in ("rising", "falling"):
            x, count = v(0), window(1)
            step = (x > _shift(x, 1)) if name == "rising" else (x < _shift(x, 1))
            return _rolling(step.astype(np.float64), count, np.sum) == count
        if name == "bars_since":
            last = _last_true(v(0))
            return np.where(last >= 0, np.arange(len(last)) - last, np.nan).astype(np.float64)
        if name == "value_when":
            return pick(v(1), _last_true(v(0)))
        if name in ("highest_since", "lowest_since"):
            return _since(v(0), v(1), highest=name == "highest_since")
        if name == "abs":
            return np.abs(v(0))
        if name in ("min", "max"):
            combine = np.minimum if name == "min" else np.maximum
            out = v(0)
            for i in range(1, len(args)):
                out = combine(out, v(i))
            return out
        if name == "stale":
            return self._stale(args[0], ctx)
        if name in SESSION_FUNCTIONS:
            return self._session(name, args[0].id, ctx)  # type: ignore[attr-defined]  # the checker allows a Name only
        raise KeyError(f"`{name}` has no value on a whole axis")

    def _session(self, name: str, session: str, ctx: Context) -> np.ndarray:
        series = self._series[ctx]
        if not len(series):
            return np.full(0, np.nan)
        days = sessions.days(SESSIONS[session], int(series.starts[0]), int(series.available[-1]))
        if name == "session_bar":
            return days.bar_number(series.starts, PERIOD_SECONDS[ctx[1]])
        # From the decision, which is the bar's close.
        return days.minutes_to_close(series.available)

    def _stale(self, node: f.Node, ctx: Context) -> np.ndarray:
        """True where any series read under `@` inside `node` last moved more than one of its periods ago."""
        moments = self._series[ctx].available
        out = np.zeros(len(moments), dtype=bool)

        def walk(n: f.Node, at: Context) -> None:
            nonlocal out
            if isinstance(n, f.At):
                value, inner = through_at(n, at)
                source = self._series[inner]
                index = align(source.available, moments)
                age = moments - pick(source.available.astype(np.float64), index)
                out |= (index < 0) | (age > PERIOD_SECONDS[inner[1]])
                walk(value, inner)
                return
            for child in children(n):
                walk(child, at)

        walk(node, ctx)
        return out

    # --- phase two: one bar, with the trade's state ---------------------------------------------------------------

    def stateful(self, node: f.Node) -> bool:
        if node not in self._stateful:
            self._stateful[node] = (
                isinstance(node, f.Name) and (node.id in POSITION or node.id in HISTORY)
                or isinstance(node, f.Call) and node.function == "at_entry"
                or any(self.stateful(c) for c in children(node))
            )
        return self._stateful[node]

    def at(self, node: f.Node, bar: int, state: State) -> float | bool:
        """`node` on decision bar `bar`. Parts without state are read from phase one."""
        if not self.stateful(node):
            value = self.vector(node)[bar]
            return bool(value) if isinstance(value, np.bool_) else float(value)
        if isinstance(node, f.Name):
            return state.name(node.id)
        if isinstance(node, f.Neg):
            return -float(self.at(node.operand, bar, state))
        if isinstance(node, f.Arith):
            left, right = float(self.at(node.left, bar, state)), float(self.at(node.right, bar, state))
            with np.errstate(divide="ignore", invalid="ignore"):
                out = float(_ARITH[node.op](left, right))
            return out if np.isfinite(out) else np.nan
        if isinstance(node, f.Compare):
            values = [float(self.at(o, bar, state)) for o in node.operands]
            return all(
                not np.isnan(a) and not np.isnan(b) and _COMPARE[op](a, b)
                for op, a, b in zip(node.ops, values, values[1:], strict=False)
            )
        if isinstance(node, f.Logic):
            values = (bool(self.at(v, bar, state)) for v in node.values)
            return all(values) if node.op == "and" else any(values)
        if isinstance(node, f.Not):
            return not bool(self.at(node.operand, bar, state))
        if isinstance(node, f.IfElse):
            branch = node.then if self.at(node.condition, bar, state) else node.otherwise
            return self.at(branch, bar, state)
        if isinstance(node, f.Call) and node.function == "at_entry":
            return float(self.vector(node.args[0])[state.entry_bar]) if state.entry_bar >= 0 else np.nan
        if isinstance(node, f.Call) and node.function in PER_BAR:
            values = [float(self.at(a, bar, state)) for a in node.args]
            if node.function == "abs":
                return abs(values[0])
            return float((np.minimum if node.function == "min" else np.maximum).reduce(values))
        raise TypeError(f"{type(node).__name__} cannot carry the trade's state")  # refused by the checker


def _shift(x: np.ndarray, bars: int) -> np.ndarray:
    if bars == 0:
        return x
    fill = False if x.dtype == bool else np.nan
    out = np.empty_like(x)
    out[:bars] = fill
    out[bars:] = x[:-bars] if bars < len(x) else x[:0]
    return out[: len(x)]


def _rolling(x: np.ndarray, n: int, reducer: Callable) -> np.ndarray:
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        out[n - 1:] = reducer(sliding_window_view(x, n), axis=1)
    return out


def _last_true(cond: np.ndarray) -> np.ndarray:
    return np.maximum.accumulate(np.where(cond, np.arange(len(cond)), -1))


def _since(cond: np.ndarray, x: np.ndarray, *, highest: bool) -> np.ndarray:
    out = np.full(len(x), np.nan)
    best = np.nan
    seen = False
    better = max if highest else min
    for i in range(len(x)):
        if cond[i]:
            seen, best = True, x[i]
        elif seen:
            best = x[i] if np.isnan(best) else (best if np.isnan(x[i]) else better(best, x[i]))
        if seen:
            out[i] = best
    return out
