"""Minutes and the hours built from them, as a test writes them — a few rows at named moments, or a seeded walk — and a
run of the engine over them with nothing read from anywhere."""

from __future__ import annotations

import numpy as np

from strategies.costs import CostModel
from strategies.document import servable, validate
from strategies.engine import Result, simulate
from strategies.series import PERIOD_SECONDS, Series

from .builders import catalogue

# A Monday, so weekdays and nights in a test read as the calendar does.
MONDAY = 1_772_409_600  # 2026-03-02T00:00:00Z
HOUR = 3600

FREE = CostModel(spread=0.0, slippage=0.0, overnight_long=0.0, overnight_short=0.0, rollover_hour=22)


def minutes(rows: dict[int, tuple[float, float, float, float]]) -> Series:
    """`{seconds after MONDAY: (open, high, low, close)}` as a minute series."""
    starts = np.array(sorted(rows), dtype=np.int64) + MONDAY
    ohlc = np.array([rows[k] for k in sorted(rows)], dtype=np.float64).reshape(-1, 4)
    columns = {name: ohlc[:, i] for i, name in enumerate(("open", "high", "low", "close"))}
    columns["volume"] = np.zeros(len(starts))
    return Series("MINUTE", starts, starts + 60, columns)


def flat(start: int, end: int, price: float) -> dict[int, tuple[float, float, float, float]]:
    return {t: (price, price, price, price) for t in range(start, end, 60)}


def walk(days: int, seed: int = 7, start_price: float = 18_000.0) -> dict[int, tuple[float, float, float, float]]:
    """Weekday minutes of a seeded random walk; weekends are absent, as a closed market is."""
    rng = np.random.default_rng(seed)
    rows: dict[int, tuple[float, float, float, float]] = {}
    price = start_price
    for day in range(days):
        if day % 7 in (5, 6):
            continue
        for minute in range(24 * 60):
            step = rng.normal(0, 3)
            high, low = price + abs(rng.normal(0, 2)), price - abs(rng.normal(0, 2))
            close = price + step
            rows[day * 86400 + minute * 60] = (price, max(high, price, close), min(low, price, close), close)
            price = close
    return rows


def bars(minute: Series, resolution: str) -> Series:
    """The bars a minute series makes at `resolution` — what the archive derives, done here the same way."""
    seconds = PERIOD_SECONDS[resolution]
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


def hours(minute: Series) -> Series:
    return bars(minute, "HOUR")


def strategy(**sections) -> dict:
    """A small HOUR document on US100; every section but those given is the plainest that passes."""
    built = {
        "schema": 1,
        "name": "test",
        "symbol": "US100",
        "timeframe": "HOUR",
        "entries": [{"side": "long", "when": "hour == 9"}],
        "exits": {"stop": "entry_price - 50"},
        "sizing": {"mode": "fixed_units", "value": 1},
    }
    built.update(sections)
    return built


def run(
    document: dict,
    minute: Series,
    *,
    costs: CostModel = FREE,
    capital: float = 10_000.0,
    range_from: int | None = None,
    range_to: int | None = None,
    params: dict[str, float] | None = None,
    margin_factor: float | None = None,
) -> Result:
    checked, problems = validate(document, catalogue(), servable({("US100", "MINUTE")}))
    assert checked is not None, problems
    series = {("US100", "MINUTE"): minute, ("US100", "HOUR"): hours(minute)}
    if document["timeframe"] not in ("MINUTE", "HOUR"):
        series[("US100", document["timeframe"])] = bars(minute, document["timeframe"])
    return simulate(
        checked, params or {}, catalogue(), series, {}, costs, capital,
        MONDAY if range_from is None else range_from,
        int(minute.available[-1]) if range_to is None else range_to,
        margin_factor=margin_factor,
    )
