"""What a checked document needs read before it can run: which indicator lines, in which context, and how far back. The
reader and the evaluator both name an indicator through `indicator_key`, so what is fetched is exactly what is looked up."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from . import formula as f
from .checking import children
from .document import Checked, contexts
from .series import PERIOD_SECONDS, Context
from .vocabulary import FUNCTIONS, RESOLUTIONS, Indicator

# Bars are counted in trading bars and read in calendar time: a weekend, a holiday and the daily break stretch one into
# the other. Generous on purpose — reading too far back costs a few rows, too short a series is a wrong warm-up.
_CALENDAR_FACTOR = 1.6
_CALENDAR_MARGIN_SECONDS = 4 * 86400


@dataclass(frozen=True)
class IndicatorKey:
    context: Context
    id: str
    params: tuple[tuple[str, float], ...]
    line: str


def indicator_key(
    call: f.Call, line: str | None, context: Context, catalogue: Mapping[str, Indicator], params: Mapping[str, float]
) -> IndicatorKey:
    entry = catalogue[call.function]
    given: dict[str, float] = {p.name: p.default for p in entry.params}
    named = dict(call.kwargs)
    for spec, arg in zip(entry.params, call.args, strict=False):
        named[spec.name] = arg
    for name, arg in named.items():
        given[name] = arg.value if isinstance(arg, f.Num) else params[arg.name]  # type: ignore[union-attr]
    return IndicatorKey(context, call.function, tuple(sorted(given.items())), line or entry.lines[0])


@dataclass(frozen=True)
class Needs:
    contexts: frozenset[Context]
    indicators: frozenset[IndicatorKey]
    # How far before the range every series is read, so the first decision in it already has its full history.
    warmup_seconds: int


def needs(checked: Checked, params: Mapping[str, float], catalogue: Mapping[str, Indicator]) -> Needs:
    d = checked.document
    decision: Context = (d.symbol, d.timeframe)
    keys: set[IndicatorKey] = set()
    lets = {name: checked.formulas[f"let.{name}"] for name in checked.let_order}
    let_reach: dict[str, int] = {}

    def reach(n: f.Node, ctx: Context) -> int:
        """Seconds of history `n` needs behind the bar it is evaluated on, collecting indicator keys on the way."""
        period = PERIOD_SECONDS[ctx[1]]
        if isinstance(n, f.Name) and n.id in lets:
            if n.id not in let_reach:
                let_reach[n.id] = reach(lets[n.id], decision)
            return let_reach[n.id]
        if isinstance(n, f.Field) and isinstance(n.value, f.Call):
            keys.add(indicator_key(n.value, n.name, ctx, catalogue, params))
            return 0
        if isinstance(n, f.Call) and n.function not in FUNCTIONS:
            keys.add(indicator_key(n, None, ctx, catalogue, params))
            return 0
        if isinstance(n, f.At):
            inner = (ctx[0], n.context) if n.context in RESOLUTIONS else (n.context, ctx[1])
            return reach(n.value, inner) + PERIOD_SECONDS[inner[1]]
        own = 0
        if isinstance(n, f.Lag):
            own = _bars(n.bars, params) * period
        elif isinstance(n, f.Call) and n.function in FUNCTIONS:
            windows = [a for a, kind in zip(n.args, FUNCTIONS[n.function].args, strict=False) if kind.value == "window"]
            own = sum(_bars(_window_of(a), params) for a in windows) * period
            if n.function in ("crosses_above", "crosses_below", "rising", "falling"):
                own += period
        return own + max((reach(c, ctx) for c in children(n)), default=0)

    deepest = max((reach(node, decision) for node in checked.formulas.values()), default=0)
    warmup = int(deepest * _CALENDAR_FACTOR) + _CALENDAR_MARGIN_SECONDS
    return Needs(frozenset(contexts(d, checked.formulas)), frozenset(keys), warmup)


def _window_of(arg: f.Node) -> int | f.Param:
    return int(arg.value) if isinstance(arg, f.Num) else arg  # type: ignore[return-value]


def _bars(bars: int | f.Param, params: Mapping[str, float]) -> int:
    return bars if isinstance(bars, int) else int(params[bars.name])
