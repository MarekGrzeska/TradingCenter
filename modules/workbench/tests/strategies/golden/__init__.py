"""Golden strategies: reference documents run on seeded synthetic minutes, their results recorded in `golden.json` beside
`ENGINE_VERSION`. A change to the engine that moves any result has to raise that number (`strategies-backtest`).

The archive's indicators are recorded too — computed once by its own kernel in `regenerate.py` — so the test reads no
archive and depends on no package but this one."""

from __future__ import annotations

import json
import pathlib
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from strategies import reports
from strategies.costs import CostModel
from strategies.document import Checked, servable, validate
from strategies.engine import simulate
from strategies.evaluate import Evaluator
from strategies.requirements import IndicatorKey, needs
from strategies.series import Series

from ..builders import catalogue
from ..market import MONDAY, minutes, walk

RECORDING = pathlib.Path(__file__).with_name("golden.json")
DAYS = 21

PROFILE = [2.5] * 7 + [1.0] * 14 + [2.5] * 3  # wide at night, narrow through the day, UTC
COSTS = CostModel(spread=PROFILE, slippage=0.3, overnight_long=0.0002, overnight_short=0.0001, rollover_hour=22)


def _bars(minute: Series, resolution: str, seconds: int) -> Series:
    buckets = minute.starts // seconds * seconds
    starts, first = np.unique(buckets, return_index=True)
    last = np.append(first[1:], len(buckets)) - 1
    columns = {
        "open": minute.columns["open"][first],
        "close": minute.columns["close"][last],
        "high": np.maximum.reduceat(minute.columns["high"], first),
        "low": np.minimum.reduceat(minute.columns["low"], first),
        "volume": np.add.reduceat(minute.columns["volume"], first),
    }
    return Series(resolution, starts, starts + seconds, columns)


def series() -> dict[tuple[str, str], Series]:
    out = {}
    for symbol, seed, price in (("US100", 11, 18_000.0), ("US500", 12, 5_000.0)):
        minute = minutes(walk(DAYS, seed=seed, start_price=price))
        out[(symbol, "MINUTE")] = minute
        out[(symbol, "HOUR")] = _bars(minute, "HOUR", 3600)
        out[(symbol, "HOUR_4")] = _bars(minute, "HOUR_4", 14400)
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
    "minute_scalp": _document(
        timeframe="MINUTE",
        entries=[{"side": "long", "when": "crosses_above(close, average(close, 15))"}],
        exits={"stop": "entry_price - 4", "target": "entry_price + 4", "max_bars": 30},
    ),
}

# The scalp runs two days: a minute strategy over three weeks is what the performance measurement is for, not this.
RANGES = {name: (MONDAY + 2 * 86400, MONDAY + (4 if name == "minute_scalp" else DAYS) * 86400) for name in DOCUMENTS}


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
            "costs": COSTS, "capital": 10_000.0, "range_from": start, "range_to": end}
    evaluator = Evaluator(document, {}, catalogue(), data, indicators)
    result = simulate(**args, evaluator=evaluator)
    d = document.document
    report = reports.build(
        result, decision=data[(d.symbol, d.timeframe)], minute=data[(d.symbol, "MINUTE")], costs=COSTS,
        capital=10_000.0, range_from=start, range_to=end,
        random_entry=reports.random_entry(result, simulate_args=args, evaluator=evaluator, seed=7, repetitions=5),
    )
    return rounded({"trades": [asdict(t) for t in result.trades], "report": report})


def rounded(value: Any) -> Any:
    """Six decimals: well under a cent at these prices, and above the last bits two machines may disagree on."""
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
