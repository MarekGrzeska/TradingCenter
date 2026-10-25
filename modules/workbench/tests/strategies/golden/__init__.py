"""Golden strategies: reference documents on seeded synthetic minutes, results and the archive's indicator lines recorded
in `golden.json` beside `ENGINE_VERSION`, which any change that moves a result has to raise."""

from __future__ import annotations

import functools
import json
import pathlib
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from strategies import reports
from strategies.costs import CostModel
from strategies.document import Checked, execution, servable, validate
from strategies.engine import simulate
from strategies.evaluate import Evaluator
from strategies.requirements import IndicatorKey, needs
from strategies.series import Series

from ..builders import catalogue
from ..market import MONDAY, bars, minutes, walk

RECORDING = pathlib.Path(__file__).with_name("golden.json")
DAYS = 21

PROFILE = [2.5] * 7 + [1.0] * 14 + [2.5] * 3  # wide at night, narrow through the day, UTC
MARGIN = 0.05
COSTS = CostModel(spread=PROFILE, slippage=0.3, overnight_long=0.0002, overnight_short=0.0001, rollover_hour=22)


def series() -> dict[tuple[str, str], Series]:
    out = {}
    for symbol, seed, price in (("US100", 11, 18_000.0), ("US500", 12, 5_000.0)):
        minute = minutes(walk(DAYS, seed=seed, start_price=price))
        out[(symbol, "MINUTE")] = minute
        out[(symbol, "MINUTE_5")] = bars(minute, "MINUTE_5")
        out[(symbol, "HOUR")] = bars(minute, "HOUR")
        out[(symbol, "HOUR_4")] = bars(minute, "HOUR_4")
    return out


_SIDED_STOP = "entry_price - 2 * at_entry(atr(14)) if position == LONG else entry_price + 2 * at_entry(atr(14))"
_SIDED_TARGET = "entry_price + 3 * at_entry(atr(14)) if position == LONG else entry_price - 3 * at_entry(atr(14))"


def _document(**sections: Any) -> dict[str, Any]:
    return {"schema": 1, "name": "golden", "symbol": "US100", "timeframe": "HOUR",
            "sizing": {"mode": "fixed_units", "value": 1}} | sections


DOCUMENTS: dict[str, dict[str, Any]] = {
    "crossover_with_costs": _document(
        entries=[
            {"side": "long", "when": "crosses_above(close, ema(20))"},
            {"side": "short", "when": "crosses_below(close, ema(20))"},
        ],
        exits={"stop": _SIDED_STOP, "target": _SIDED_TARGET, "max_bars": 24},
        sizing={"mode": "risk_fraction", "value": 0.01},
    ),
    "stop_entry_and_trail": _document(
        let={"ceiling": "highest(high, 10)[1]", "slow": "average(close, 30)"},
        entries=[{"side": "long", "when": "close > slow and close < ceiling",
                  "order": {"type": "stop", "price": "ceiling", "expires_bars": 3}}],
        exits={"stop": "entry_price - 2 * at_entry(atr(14))", "trail": {"after_r": 0.5, "distance": "0.8 * atr(14)"},
               "when": "crosses_below(close, slow)"},
        sizing={"mode": "fixed_units", "value": 2},
    ),
    "other_contexts": _document(
        let={
            "h4_up": "close @ HOUR_4 > open @ HOUR_4",
            "broad_up": "close @ US500 @ HOUR_4 > average(close, 20) @ US500 @ HOUR_4",
        },
        entries=[
            {"side": "long", "when": "close > average(close, 50) and h4_up and broad_up and not stale(close @ US500 @ HOUR_4)"},
            {"side": "short", "when": "close < average(close, 50) and not h4_up and not broad_up"},
        ],
        exits={"stop": "entry_price - 40 if position == LONG else entry_price + 40",
               "target": "entry_price + 60 if position == LONG else entry_price - 60"},
    ),
    "state_and_limits": _document(
        entries=[{"side": "long", "when": "crosses_above(close, ema(20)) and losses_in_row < 4"}],
        exits={"stop": "entry_price - 60", "when": "open_r > 1 or bars_in_trade > 10"},
        limits={"daily_stop_r": -1.5, "no_entry": "weekday == FRIDAY and hour >= 18"},
    ),
    # The operator's strategy of 25 October 2026, across the US change of time on 8 March: no stop, held to five minutes
    # before New York closes, sized by a 5% deposit.
    "session_without_a_stop": _document(
        timeframe="MINUTE_5",
        entries=[
            {"side": "long", "when": "session_bar(NEW_YORK) == 1 and close > ema(12)"},
            {"side": "short", "when": "session_bar(NEW_YORK) == 1 and close < ema(12)"},
        ],
        exits={"when": "minutes_to_session_close(NEW_YORK) <= 5"},
        sizing={"mode": "margin_fraction", "value": 0.05},
    ),
    "minute_scalp": _document(
        timeframe="MINUTE",
        entries=[{"side": "long", "when": "crosses_above(close, average(close, 15))"}],
        exits={"stop": "entry_price - 4", "target": "entry_price + 4", "max_bars": 30},
    ),
}

# The scalp runs two days: a minute strategy over three weeks is what the performance measurement is for, not this.
RANGES = {name: (MONDAY + 2 * 86400, MONDAY + (4 if name == "minute_scalp" else DAYS) * 86400) for name in DOCUMENTS}


@functools.cache
def checked(name: str) -> Checked:
    found, problems = validate(DOCUMENTS[name], catalogue(), servable({("US100", "MINUTE"), ("US500", "MINUTE")}))
    assert found is not None, (name, problems)
    return found


def indicator_keys() -> set[IndicatorKey]:
    return {key for name in DOCUMENTS for key in needs(checked(name), {}, catalogue()).indicators}


@dataclass(frozen=True)
class Case:
    name: str
    result: dict[str, Any]


def run(name: str, data: dict[tuple[str, str], Series], indicators: dict[IndicatorKey, np.ndarray]) -> dict[str, Any]:
    document = checked(name)
    start, end = RANGES[name]
    args = {"checked": document, "params": {}, "catalogue": catalogue(), "series": data, "indicators": indicators,
            "costs": COSTS, "capital": 10_000.0, "range_from": start, "range_to": end, "margin_factor": MARGIN}
    evaluator = Evaluator(document, {}, catalogue(), data, indicators)
    result = simulate(**args, evaluator=evaluator)
    d = document.document
    report = reports.build(
        result, decision=data[(d.symbol, d.timeframe)], execution=data[(d.symbol, execution(d))], costs=COSTS,
        capital=10_000.0, range_from=start, range_to=end,
        random_entry=reports.random_entry(result, simulate_args=args, evaluator=evaluator, seed=7, repetitions=5),
    )
    return rounded({"trades": [asdict(t) for t in result.trades], "report": report})


def rounded(value: Any) -> Any:
    """Six decimals, to keep the recording readable; comparison is `same`, with a tolerance, not equality."""
    if isinstance(value, float):
        return None if not np.isfinite(value) else round(value, 6)
    if isinstance(value, dict):
        return {k: rounded(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [rounded(v) for v in value]
    return value


def load() -> dict[str, Any]:
    return json.loads(RECORDING.read_text(encoding="utf-8"))


def recorded_indicators(recording: dict[str, Any], data: dict[tuple[str, str], Series]) -> dict[IndicatorKey, np.ndarray]:
    out = {}
    for item in recording["indicators"]:
        key = IndicatorKey(tuple(item["context"]), item["id"], tuple(map(tuple, item["params"])), item["line"])  # type: ignore[arg-type]
        out[key] = np.array([np.nan if v is None else v for v in item["values"]], dtype=np.float64)
        assert len(out[key]) == len(data[key.context])
    return out


def same(found: Any, recorded: Any, path: str = "") -> str | None:
    """Where `found` differs from `recorded`, or `None`. Numbers within 1e-6 are the same: two machines may disagree in
    the last bits, and a rounding boundary would turn that into a difference."""
    if isinstance(recorded, dict) and isinstance(found, dict):
        if found.keys() != recorded.keys():
            return f"{path}: keys {sorted(found.keys() ^ recorded.keys())}"
        return next((d for k in recorded if (d := same(found[k], recorded[k], f"{path}.{k}"))), None)
    if isinstance(recorded, list) and isinstance(found, list):
        if len(found) != len(recorded):
            return f"{path}: {len(found)} items, recorded {len(recorded)}"
        return next((d for i, (a, b) in enumerate(zip(found, recorded, strict=True)) if (d := same(a, b, f"{path}[{i}]"))), None)
    numbers = (int, float)
    if isinstance(recorded, numbers) and isinstance(found, numbers) and not isinstance(recorded, bool):
        return None if abs(found - recorded) <= 1e-6 + 1e-9 * abs(recorded) else f"{path}: {found} vs {recorded}"
    return None if found == recorded else f"{path}: {found!r} vs {recorded!r}"
