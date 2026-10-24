"""The run itself: decisions on the close of each bar of the strategy's timeframe, fills settled on the traded
instrument's minutes, one position at a time. Pure — arrays in, trades out — so it can run in a worker process with
nothing but its arguments (design D5), and so the same inputs always give the same trades."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

import numpy as np

from .costs import CostModel
from .document import Checked
from .evaluate import Evaluator, State
from .requirements import IndicatorKey
from .series import Context, Series
from .vocabulary import Indicator

# Raised by every change that moves a result — a fill rule, a cost, a rounding. Recorded in each report, and the golden
# strategies refuse a changed result under an unchanged number (`strategies-backtest`).
ENGINE_VERSION = 1


@dataclass(frozen=True)
class Trade:
    side: str
    signal_bar: int
    entry_time: int
    entry_price: float
    exit_time: int
    exit_price: float
    units: float
    initial_stop: float
    result_r: float
    result_money: float
    costs: dict[str, float]
    exit_reason: str
    pessimistic: bool


@dataclass(frozen=True)
class Result:
    trades: list[Trade]
    # Signals that became no trade: a stop on the wrong side of the fill, or no stop at all where it was evaluated.
    rejected_entries: int
    decision_bars: int


@dataclass
class _Order:
    side: int
    kind: str
    price: float
    signal_bar: int
    expires_at_bar: int | None


@dataclass
class _Position:
    side: int
    entry_time: int
    entry_price: float
    entry_bar: int
    signal_bar: int
    units: float
    stop: float
    initial_stop: float
    target: float
    risk: float
    pessimistic: bool = False
    slippage_paid: float = 0.0
    spread_paid: float = 0.0
    exit_at_next_minute: str | None = None
    trailed: bool = False


@dataclass
class _Book:
    capital: float
    realized: float = 0.0
    day: int = -1
    day_r: float = 0.0
    trades_today: int = 0
    losses_in_row: int = 0
    last_trade_r: float = 0.0
    trades: list[Trade] = field(default_factory=list)
    rejected: int = 0


def simulate(
    checked: Checked,
    params: Mapping[str, float],
    catalogue: Mapping[str, Indicator],
    series: Mapping[Context, Series],
    indicators: Mapping[IndicatorKey, np.ndarray],
    costs: CostModel,
    capital: float,
    range_from: int,
    range_to: int,
) -> Result:
    d = checked.document
    evaluator = Evaluator(checked, params, catalogue, series, indicators)
    decision = series[(d.symbol, d.timeframe)]
    minute = series[(d.symbol, "MINUTE")]
    entry_conditions = [checked.formulas[f"entries[{i}].when"] for i in range(len(d.entries))]
    book = _Book(capital)
    position: _Position | None = None
    order: _Order | None = None

    bars = [i for i in range(len(decision)) if range_from <= decision.starts[i] and decision.available[i] <= range_to]
    previous_moment = range_from
    for bar in bars:
        moment = int(decision.available[bar])
        # Every minute between the last decision and this one: orders fill, stops and targets are touched.
        lo, hi = np.searchsorted(minute.starts, [previous_moment, moment], side="left")
        for m in range(int(lo), int(hi)):
            if position is None and order is None:
                break
            position, order = _minute(m, minute, position, order, costs, book, checked, evaluator, bar)
        previous_moment = moment
        if order is not None and order.expires_at_bar is not None and bar >= order.expires_at_bar:
            order = None
        _new_day(book, moment)

        state = _state(position, book, bar, decision, costs, moment)
        if position is not None:
            _trail(position, checked, evaluator, bar, state, decision)
            if d.exits.when is not None and evaluator.at(checked.formulas["exits.when"], bar, state):
                position.exit_at_next_minute = "when"
            elif d.exits.max_bars is not None and bar - position.entry_bar >= d.exits.max_bars:
                position.exit_at_next_minute = "max_bars"
            continue
        if order is not None or _blocked(checked, evaluator, bar, state, book):
            continue
        for index, condition in enumerate(entry_conditions):
            if evaluator.at(condition, bar, state):
                entry = d.entries[index]
                price = (
                    float(evaluator.at(checked.formulas[f"entries[{index}].order.price"], bar, state))
                    if entry.order.price is not None else np.nan
                )
                expires = None if entry.order.expires_bars is None else bar + entry.order.expires_bars
                order = _Order(1 if entry.side == "long" else -1, entry.order.type, price, bar, expires)
                break

    # What the last decision leaves in flight settles on the minutes up to the end of the range.
    lo, hi = np.searchsorted(minute.starts, [previous_moment, range_to], side="left")
    for m in range(int(lo), int(hi)):
        if position is None:
            break
        position, order = _minute(m, minute, position, None, costs, book, checked, evaluator, bars[-1] if bars else 0)
    if position is not None:
        last = int(hi) - 1 if hi > 0 else 0
        price = minute.columns["close"][last] + (costs.spread_at(int(minute.starts[last])) if position.side < 0 else 0.0)
        _close(position, int(minute.available[last]), price, "end_of_range", book, costs)
    return Result(book.trades, book.rejected, len(bars))


def _state(position: _Position | None, book: _Book, bar: int, decision: Series, costs: CostModel, moment: int) -> State:
    state = State(losses_in_row=book.losses_in_row, last_trade_r=book.last_trade_r, trades_today=book.trades_today)
    if position is not None:
        close = decision.columns["close"][bar]
        exit_price = close if position.side > 0 else close + costs.spread_at(moment)
        state.position = position.side
        state.entry_price = position.entry_price
        state.entry_bar = position.signal_bar
        state.bars_in_trade = bar - position.entry_bar
        financing = _financing(position, moment, costs)
        state.open_r = (position.side * (exit_price - position.entry_price) * position.units - financing) / (
            position.units * position.risk
        )
    return state


def _trail(position: _Position, checked: Checked, evaluator: Evaluator, bar: int, state: State, decision: Series) -> None:
    trail = checked.document.exits.trail
    if trail is None or not state.open_r >= trail.after_r:
        return
    distance = float(evaluator.at(checked.formulas["exits.trail.distance"], bar, state))
    if np.isnan(distance) or distance <= 0:
        return
    close = decision.columns["close"][bar]
    candidate = close - distance if position.side > 0 else close + distance
    if position.side * (candidate - position.stop) > 0:
        position.stop = candidate
        position.trailed = True


def _blocked(checked: Checked, evaluator: Evaluator, bar: int, state: State, book: _Book) -> bool:
    limits = checked.document.limits
    if limits.daily_stop_r is not None and book.day_r <= limits.daily_stop_r:
        return True
    return limits.no_entry is not None and bool(evaluator.at(checked.formulas["limits.no_entry"], bar, state))


def _new_day(book: _Book, moment: int) -> None:
    day = moment // 86400
    if day != book.day:
        book.day, book.day_r, book.trades_today = day, 0.0, 0


def _minute(
    m: int,
    minute: Series,
    position: _Position | None,
    order: _Order | None,
    costs: CostModel,
    book: _Book,
    checked: Checked,
    evaluator: Evaluator,
    bar: int,
) -> tuple[_Position | None, _Order | None]:
    start = int(minute.starts[m])
    spread = costs.spread_at(start)
    bid = {k: minute.columns[k][m] for k in ("open", "high", "low", "close")}
    if np.isnan(bid["open"]):
        return position, order
    ask = {k: v + spread for k, v in bid.items()}

    if position is not None and position.exit_at_next_minute is not None:
        price = bid["open"] - costs.slippage if position.side > 0 else ask["open"] + costs.slippage
        position.slippage_paid += costs.slippage
        _close(position, start, price, position.exit_at_next_minute, book, costs)
        return None, order

    entered_now = False
    if position is None and order is not None:
        fill = _fill(order, bid, ask, costs)
        if fill is None:
            return None, order
        price, slipped = fill
        position = _open(order, price, slipped, start, costs, checked, evaluator, book, bar)
        order = None
        if position is None:
            return None, None
        entered_now = True

    if position is None:
        return None, order
    exit_side = bid if position.side > 0 else ask
    stop_hit = exit_side["low"] <= position.stop if position.side > 0 else exit_side["high"] >= position.stop
    target_hit = not np.isnan(position.target) and (
        exit_side["high"] >= position.target if position.side > 0 else exit_side["low"] <= position.target
    )
    if stop_hit:
        # Within one minute the data cannot say what came first; the worse order is assumed and marked as assumed.
        if target_hit or entered_now:
            position.pessimistic = True
        gapped = exit_side["open"] <= position.stop if position.side > 0 else exit_side["open"] >= position.stop
        level = exit_side["open"] if gapped else position.stop
        price = level - costs.slippage if position.side > 0 else level + costs.slippage
        position.slippage_paid += costs.slippage
        reason = "trail" if position.trailed else "stop"
        _close(position, start, price, reason, book, costs)
        return None, order
    if target_hit and not entered_now:
        gapped = exit_side["open"] >= position.target if position.side > 0 else exit_side["open"] <= position.target
        _close(position, start, exit_side["open"] if gapped else position.target, "target", book, costs)
        return None, order
    return position, order


def _fill(order: _Order, bid: dict[str, float], ask: dict[str, float], costs: CostModel) -> tuple[float, bool] | None:
    """The price an entry order fills at in this minute, and whether it paid slippage — or `None` if it does not fill."""
    take = ask if order.side > 0 else bid
    slip = costs.slippage * order.side
    if order.kind == "market":
        return take["open"] + slip, True
    if np.isnan(order.price):
        return None
    if order.kind == "stop":
        triggered = take["high"] >= order.price if order.side > 0 else take["low"] <= order.price
        if not triggered:
            return None
        worse = max(order.price, take["open"]) if order.side > 0 else min(order.price, take["open"])
        return worse + slip, True
    triggered = take["low"] <= order.price if order.side > 0 else take["high"] >= order.price
    if not triggered:
        return None
    better = min(order.price, take["open"]) if order.side > 0 else max(order.price, take["open"])
    return better, False


def _open(
    order: _Order,
    price: float,
    slipped: bool,
    moment: int,
    costs: CostModel,
    checked: Checked,
    evaluator: Evaluator,
    book: _Book,
    bar: int,
) -> _Position | None:
    """The position an order became, with its stop and target computed once, here — or `None` when the stop it computes
    to is no stop (missing, or on the wrong side of the fill), which is counted, never traded."""
    state = State(
        position=order.side, entry_price=price, entry_bar=order.signal_bar, bars_in_trade=0, open_r=0.0,
        losses_in_row=book.losses_in_row, last_trade_r=book.last_trade_r, trades_today=book.trades_today,
    )
    d = checked.document
    stop = float(evaluator.at(checked.formulas["exits.stop"], order.signal_bar, state))
    target = (
        float(evaluator.at(checked.formulas["exits.target"], order.signal_bar, state))
        if d.exits.target is not None else np.nan
    )
    risk = order.side * (price - stop)
    if np.isnan(stop) or risk <= 0:
        book.rejected += 1
        return None
    equity = book.capital + book.realized
    units = d.sizing.value if d.sizing.mode == "fixed_units" else equity * d.sizing.value / risk
    if not units > 0:
        book.rejected += 1
        return None
    _new_day(book, moment)
    book.trades_today += 1
    return _Position(
        side=order.side, entry_time=moment, entry_price=price, entry_bar=bar, signal_bar=order.signal_bar,
        units=units, stop=stop, initial_stop=stop, target=target, risk=risk,
        slippage_paid=costs.slippage if slipped else 0.0,
        spread_paid=costs.spread_at(moment) if order.side > 0 else 0.0,
    )


def _financing(position: _Position, moment: int, costs: CostModel) -> float:
    rate = costs.overnight_long if position.side > 0 else costs.overnight_short
    return costs.nights(position.entry_time, moment) * rate * position.units * position.entry_price


def _close(position: _Position, moment: int, price: float, reason: str, book: _Book, costs: CostModel) -> None:
    financing = _financing(position, moment, costs)
    spread = position.spread_paid if position.side > 0 else costs.spread_at(moment)
    money = position.side * (price - position.entry_price) * position.units - financing
    r = money / (position.units * position.risk)
    _new_day(book, moment)
    book.realized += money
    book.day_r += r
    book.losses_in_row = book.losses_in_row + 1 if r < 0 else 0
    book.last_trade_r = r
    book.trades.append(Trade(
        side="long" if position.side > 0 else "short",
        signal_bar=position.signal_bar,
        entry_time=position.entry_time,
        entry_price=position.entry_price,
        exit_time=moment,
        exit_price=price,
        units=position.units,
        initial_stop=position.initial_stop,
        result_r=r,
        result_money=money,
        costs={
            "spread": spread * position.units,
            "slippage": position.slippage_paid * position.units,
            "financing": financing,
        },
        exit_reason=reason,
        pessimistic=position.pessimistic,
    ))
