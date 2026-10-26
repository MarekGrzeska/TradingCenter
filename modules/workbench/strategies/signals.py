"""What the engine would do next, for a team trading the strategy on the demo account (`strategies-tools`, "Sygnał
strategii jest decyzją silnika backtestu"). The backtest's own `simulate` over a short window ending at the last closed
bar, read before it settles what is in flight (design D1) — never a second reading of the rules. Writes nothing."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, Field
from tc_runtime.db import Conn

from . import costs_store, documents, margins, store
from .archive import Archive
from .document import Checked, execution
from .engine import InFlight, simulate
from .reading import bars_without_minutes, read
from .runs import NO_COSTS
from .series import PERIOD_SECONDS, Series, moment

# Decision bars before the last closed one (design D2): about a week of M5 trading. A position the engine opened before
# the window is invisible to it, so the answer names where the window starts.
WINDOW_BARS = 2_000
# Off the loop, and bounded: a team's turn waits on this.
TIMEOUT_SECONDS = 20.0
# Equity the window is simulated with. Decisions do not depend on it; the size the team trades is its own balance's.
CAPITAL = 10_000.0

Action = Literal["enter", "order_working", "exit", "hold", "none"]


class SignalRefused(Exception):
    """A signal that cannot be given — said in words the caller can act on, never answered as "do nothing"."""


class Order(BaseModel):
    side: str
    kind: str = Field(description="market, stop or limit")
    price: float | None = Field(description="null for a market order, which takes the next open")
    signalled_at: str


class Position(BaseModel):
    side: str
    entered_at: str
    entry_price: float
    stop: float | None
    target: float | None


class Signal(BaseModel):
    strategy_id: int
    revision: int
    symbol: str
    timeframe: str
    bar_closed_at: str = Field(description="UTC close of the bar the decision was made on")
    bar_age_seconds: int
    action: Action
    order: Order | None = None
    position: Position | None = Field(default=None, description="the engine's own position in the window, not the account's")
    exit_reason: str | None = None
    sizing: dict[str, Any] = Field(description="the document's rule; units come from the account's own balance")
    params: dict[str, float]
    window_from: str
    costs_source: str


def _iso(seconds: int) -> str:
    return moment(seconds).isoformat().replace("+00:00", "Z")


def _number(value: float) -> float | None:
    return None if np.isnan(value) else float(value)


def decide(in_flight: InFlight, decision: Series) -> tuple[Action, Order | None, Position | None, str | None]:
    """The engine's state after its last decision, as the action it calls for."""
    order = position = None
    if in_flight.order is not None:
        o = in_flight.order
        order = Order(side=o.side, kind=o.kind, price=_number(o.price),
                      signalled_at=_iso(int(decision.available[o.signal_bar])))
        action: Action = "enter" if o.signal_bar == in_flight.last_bar else "order_working"
        return action, order, None, None
    if in_flight.position is not None:
        p = in_flight.position
        position = Position(side=p.side, entered_at=_iso(p.entry_time), entry_price=p.entry_price,
                            stop=_number(p.stop), target=_number(p.target))
        return ("exit" if p.exit_due is not None else "hold"), None, position, p.exit_due
    return "none", None, None, None


def _window(timeframe: str, now: int) -> tuple[int, int]:
    """[from, to) ending at the close of the last bar that has closed by `now`."""
    period = PERIOD_SECONDS[timeframe]
    last_close = now // period * period
    return last_close - WINDOW_BARS * period, last_close


async def signal(conn: Conn, archive: Archive, strategy_id: int, revision: int, now: int) -> Signal:
    try:
        found = await store.get_revision(conn, strategy_id, revision)
    except store.NotFound:
        raise SignalRefused(f"strategy {strategy_id} has no revision {revision}") from None
    checked, problems = await documents.check(found.document, archive)
    if checked is None:
        listed = "; ".join(f"{p.path}: {p.message}" for p in problems[:3])
        raise SignalRefused(f"revision {revision} no longer passes its checks: {listed}")
    d = checked.document
    margin_factor = None
    if d.sizing.mode == "margin_fraction":
        margin = await margins.get(conn, d.symbol)
        if margin is None:
            raise SignalRefused(f"{d.symbol}'s deposit has never been read off the broker; run a backtest of this "
                                "strategy first, which reads it")
        margin_factor = margin.margin_factor
    profile = await costs_store.get(conn, d.symbol)
    costs, costs_source = (NO_COSTS, "none") if profile is None else (profile.costs, profile.source)

    declared: Mapping[str, Mapping[str, float]] = found.document.get("params", {})
    params = {name: float(spec["default"]) for name, spec in declared.items()}
    catalogue, _ = await archive.check_inputs()
    start, end = _window(d.timeframe, now)
    inputs = await read(archive, checked, params, catalogue, start, end)
    decision = inputs.series[(d.symbol, d.timeframe)]
    _refuse_a_missing_last_bar(decision, d.timeframe, end)
    if execution(d) == "MINUTE":
        hole = bars_without_minutes(decision, inputs.series[(d.symbol, "MINUTE")], start, end)
        if hole is not None:
            raise SignalRefused(hole)

    result = await asyncio.wait_for(
        asyncio.to_thread(_simulate, checked, params, catalogue, inputs, costs, start, end, margin_factor),
        TIMEOUT_SECONDS,
    )
    assert result.in_flight is not None and result.in_flight.last_bar is not None
    action, order, position, exit_reason = decide(result.in_flight, decision)
    closed_at = int(decision.available[result.in_flight.last_bar])
    return Signal(
        strategy_id=strategy_id, revision=found.n, symbol=d.symbol, timeframe=d.timeframe,
        bar_closed_at=_iso(closed_at), bar_age_seconds=now - closed_at, action=action, order=order,
        position=position, exit_reason=exit_reason, sizing=d.sizing.model_dump(), params=params,
        window_from=_iso(start), costs_source=costs_source,
    )


def _refuse_a_missing_last_bar(decision: Series, timeframe: str, end: int) -> None:
    closed = decision.available[decision.available <= end]
    if len(closed) and int(closed[-1]) == end:
        return
    newest = "none in the window" if not len(closed) else _iso(int(closed[-1]))
    raise SignalRefused(
        f"the archive has no {timeframe} bar closing at {_iso(end)} (newest: {newest}) — the market is shut or the "
        "archive is behind; ask again after the next bar closes"
    )


def _simulate(checked: Checked, params, catalogue, inputs, costs, start: int, end: int, margin_factor):
    return simulate(checked, params, catalogue, inputs.series, inputs.indicators, costs, CAPITAL, start, end,
                    margin_factor=margin_factor)
