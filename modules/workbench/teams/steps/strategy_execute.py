"""`strategy_execute`: the team's own position follows the strategy engine's. Reads, then one pure decision, then at most one
write — the decision is `decide`, tested as a table; everything around it only gathers its inputs and carries it out."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, TypeGuard

from ..contract import StepDefinition
from ..store import AttemptAlreadyMade
from ..tools import ToolOutcomeKind
from .catalogue import StrategyExecuteParams
from .runtime_types import StepContext

Decision = Literal["entered", "exited", "no_action", "skipped", "refused", "unknown", "unsupported"]

# The engine's sides, as the account tools spell an order's direction.
_DIRECTION = {"long": "BUY", "short": "SELL"}
_SIDE = {"BUY": "long", "SELL": "short"}
_POLL_SECONDS = 1.0
# Each ask reads a week of the archive; doubling to this keeps a 30 s wait to about eight of them.
_POLL_CEILING_SECONDS = 5.0


@dataclass(frozen=True)
class Own:
    """This team's position, as the account shows it and as its own order row placed it."""

    position_id: str
    side: str
    placed_at: datetime


@dataclass(frozen=True)
class Seen:
    """Everything `decide` reads, already parsed."""

    signal: dict[str, Any]
    params: StrategyExecuteParams
    symbol_positions: int
    symbol_orders: int
    own: Own | None
    # More than one own position, or an own order that never named its position beside one nobody claims: no guess.
    own_unclear: str | None = None


@dataclass(frozen=True)
class Action:
    kind: Literal["enter", "close", "none"]
    decision: Decision
    reason: str | None = None
    side: str | None = None
    position_id: str | None = None


def _iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


def decide(seen: Seen) -> Action:
    """The whole of the recipe's judgement, without I/O. Enter only on a fresh `enter` onto a flat account; close the
    team's own position when the engine leaves it; anything this cannot read unambiguously is `unknown`, never a guess."""
    signal = seen.signal
    order = signal.get("order") or {}
    engine = signal.get("position")
    action = signal.get("action")

    if signal.get("symbol") != seen.params.symbol:
        return Action(
            "none",
            "unsupported",
            f"the strategy trades {signal.get('symbol')!r} and this step is set to {seen.params.symbol!r}",
        )
    if seen.own_unclear is not None:
        return Action("none", "unknown", seen.own_unclear)

    if seen.own is not None:
        window_from = signal.get("window_from")
        if window_from is not None and seen.own.placed_at < _iso(window_from):
            return Action(
                "none",
                "unknown",
                f"this team's position {seen.own.position_id} opened before the engine's window "
                f"({window_from}); the engine cannot see it, so the operator decides",
            )
        if action == "enter" and order.get("side") == seen.own.side:
            # The engine fills its own entry at the next bar's open; until then this team's position is that entry.
            return Action(
                "none",
                "skipped",
                f"the entry on this signal bar was already made: this team's position {seen.own.position_id}",
            )
        engine_side = engine.get("side") if isinstance(engine, dict) else None
        if action == "exit" or engine_side != seen.own.side:
            if action == "exit":
                why = "the engine signals exit"
            elif engine_side is not None:
                why = f"the engine holds the opposite side ({engine_side})"
            elif action == "enter":
                why = f"the engine is entering the opposite side ({order.get('side')})"
            else:
                why = "the engine holds no position"
            return Action("close", "exited", why, side=seen.own.side, position_id=seen.own.position_id)
        return Action("none", "no_action", "this team's position matches the engine's")

    unsupported = _unsupported(signal)
    if unsupported is not None:
        return Action("none", "unsupported", unsupported)
    if action != "enter":
        return Action("none", "no_action", f"the engine's action is {action!r}")
    side = order.get("side")
    if side not in _DIRECTION:
        return Action("none", "unknown", f"the signal's order side {side!r} is not long or short")
    limit = seen.params.max_bar_age_seconds
    age = signal.get("bar_age_seconds")
    if limit is not None and isinstance(age, int | float) and age > limit:
        return Action("none", "skipped", f"the signal bar is {age}s old, over the {limit}s allowed")
    if seen.symbol_positions or seen.symbol_orders:
        return Action(
            "none",
            "skipped",
            f"the account already holds {seen.symbol_positions} position(s) and {seen.symbol_orders} working "
            f"order(s) on {seen.params.symbol}",
        )
    return Action("enter", "entered", side=side)


def _unsupported(signal: dict[str, Any]) -> str | None:
    """What keeps this recipe from entering, read off the document rather than the engine's position, which an entry
    never has. A position it could not protect is never opened; one already open is still closed when the engine leaves."""
    order = signal.get("order") or {}
    if order and order.get("kind") not in (None, "market"):
        return f"the signal's order is {order.get('kind')!r}; this recipe places market orders only"
    exits = signal.get("exits")
    if not isinstance(exits, list):
        return "the signal does not say which exits the strategy carries"
    if exits:
        return f"the strategy carries {', '.join(map(str, exits))}, which this recipe does not execute"
    return None


@dataclass
class _Result:
    started_at: datetime
    decision: Decision = "unknown"
    reason: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    timing: dict[str, str] = field(default_factory=dict)

    def mark(self, name: str, at: datetime) -> None:
        self.timing[name] = at.isoformat()

    def out(self, decision: Decision, reason: str | None, summary: str) -> dict[str, Any]:
        self.decision, self.reason = decision, reason
        return {
            "decision": decision,
            "reason": reason,
            "summary": summary,
            **self.extra,
            "timing": {"started": self.started_at.isoformat(), **self.timing},
        }


def _payload(text: str) -> Any:
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return None
    if isinstance(data, dict) and set(data) == {"result"}:
        return data["result"]
    return data


def _now() -> datetime:
    return datetime.now(UTC)


async def execute(
    step: StepDefinition,
    ctx: StepContext,
    *,
    now: Callable[[], datetime] = _now,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> dict[str, Any]:
    params = StrategyExecuteParams.model_validate(step.params)
    result = _Result(started_at=now())
    label = f"{params.symbol} strategy {params.strategy_id}/{params.revision}"

    signal = await _signal(ctx, params, result, now=now, sleep=sleep)
    if isinstance(signal, tuple):
        decision, why = signal
        return result.out(decision, why, f"{label}: no signal — {why}")
    result.mark("signal_seen", now())
    result.extra["signal"] = {
        key: signal.get(key) for key in ("action", "bar_closed_at", "bar_age_seconds", "order", "position", "exit_reason")
    }

    positions, orders, balance, placed = await asyncio.gather(
        ctx.call("get_positions", {}),
        ctx.call("get_working_orders", {}),
        ctx.call("get_balance", {}),
        ctx.placed_orders(params.symbol),
    )
    for name, outcome in (("get_positions", positions), ("get_working_orders", orders), ("get_balance", balance)):
        if not outcome.ok:
            return result.out("unknown", f"{name} did not answer: {outcome.text}", f"{label}: account unreadable")
    position_rows = [row for row in _payload(positions.text) or [] if row.get("symbol") == params.symbol]
    order_rows = [row for row in _payload(orders.text) or [] if row.get("symbol") == params.symbol]
    own, unclear = _own_position(position_rows, placed, signal.get("window_from"))

    action = decide(
        Seen(
            signal=signal,
            params=params,
            symbol_positions=len(position_rows),
            symbol_orders=len(order_rows),
            own=own,
            own_unclear=unclear,
        )
    )
    if action.kind == "none":
        return result.out(action.decision, action.reason, f"{label}: {action.decision} — {action.reason}")

    bar = signal.get("bar_closed_at")
    base_key = f"{ctx.team_id}:{ctx.key}:{params.strategy_id}:{params.revision}:{bar}"
    if action.kind == "close":
        return await _close(ctx, action, f"{base_key}:exit", result, label, now=now)
    return await _enter(ctx, params, signal, _payload(balance.text), action, f"{base_key}:enter", result, label, now=now)


async def _signal(ctx, params, result, *, now, sleep) -> dict[str, Any] | tuple[Decision, str]:
    """The engine's answer. A refusal is the engine's own words, most often the archive behind on the bar, so it is asked
    again, backing off, until the wait is over; a tool that did not answer, or an answer this cannot read, is `unknown`."""
    deadline = result.started_at.timestamp() + params.wait_for_bar_seconds
    pause = _POLL_SECONDS
    while True:
        outcome = await ctx.call(
            "strategy_signal", {"strategy_id": params.strategy_id, "revision": params.revision}
        )
        if outcome.ok:
            data = _payload(outcome.text)
            if isinstance(data, dict):
                return data
            return "unknown", f"strategy_signal answered something unreadable: {outcome.text[:200]}"
        if outcome.kind is not ToolOutcomeKind.REFUSED:
            return "unknown", f"strategy_signal did not answer: {outcome.text}"
        remaining = deadline - now().timestamp()
        if remaining <= 0:
            return "skipped", outcome.text
        await sleep(min(pause, remaining))
        pause = min(pause * 2, _POLL_CEILING_SECONDS)


def _own_position(
    positions: list[dict[str, Any]], placed: list[dict[str, Any]], window_from: str | None
) -> tuple[Own | None, str | None]:
    """The position one of this team's own orders opened, still on the account. Two own positions are not a state this
    recipe creates, and an own order that never named its position, beside a position no order claims, may have opened
    it: both are reported rather than resolved."""
    by_id = {str(row.get("id")): row for row in positions}
    mine: list[tuple[dict[str, Any], dict[str, Any]]] = []
    nameless: list[dict[str, Any]] = []
    for order in placed:
        candidates = [str(c) for c in (order.get("provider_order_id"), order.get("reference")) if c is not None]
        hit = next((by_id[c] for c in candidates if c in by_id), None)
        if hit is not None:
            mine.append((hit, order))
        elif order.get("status") != "settled" or order.get("provider_order_id") is None:
            nameless.append(order)

    claimed = {str(row["id"]) for row, _order in mine}
    unclaimed = [row for row in positions if str(row.get("id")) not in claimed]
    since = _iso(window_from) if window_from is not None else None
    recent = [order for order in nameless if since is None or order["created_at"] >= since]
    if unclaimed and recent:
        order = recent[0]
        return None, (
            f"this team's order {order.get('reference') or order.get('id')} ({order.get('status')}, placed "
            f"{order['created_at']}) never named the position it opened, and the account holds {len(unclaimed)} "
            "position(s) on the symbol no order of this team claims; the operator decides"
        )
    if not mine:
        return None, None
    if len(claimed) > 1:
        return None, f"this team holds more than one position on the symbol ({sorted(claimed)}); the operator decides"
    row, order = mine[0]
    side = _SIDE.get(str(row.get("direction")))
    if side is None:
        return None, f"position {row['id']} has direction {row.get('direction')!r}"
    return Own(position_id=str(row["id"]), side=side, placed_at=order["created_at"]), None


async def _close(ctx, action: Action, attempt_key: str, result: _Result, label: str, *, now) -> dict[str, Any]:
    result.mark("order_sent", now())
    try:
        outcome = await ctx.call("close_position", {"position_id": action.position_id}, attempt_key=attempt_key)
    except AttemptAlreadyMade:
        return result.out("skipped", "an exit on this signal bar was already attempted", f"{label}: exit already attempted")
    result.mark("order_answered", now())
    reply = _payload(outcome.text) if outcome.ok else None
    result.extra["order"] = reply if outcome.ok else outcome.text
    result.extra["position_id"] = action.position_id
    if _settled(reply):
        return result.out("exited", action.reason, f"{label}: closed {action.side} position {action.position_id} — {action.reason}")
    if outcome.settles_as_refused:
        return result.out("refused", outcome.text, f"{label}: close of {action.position_id} refused — {outcome.text}")
    return result.out(
        "unknown", outcome.text, f"{label}: close of {action.position_id} has no known outcome — check the account"
    )


def _settled(reply: Any) -> TypeGuard[dict[str, Any]]:
    """A write the provider confirmed. `unsettled` is a PENDING the account may still turn into anything."""
    return isinstance(reply, dict) and reply.get("outcome") == "settled"


async def _enter(
    ctx, params: StrategyExecuteParams, signal, balance, action: Action, attempt_key: str, result: _Result, label: str, *, now
) -> dict[str, Any]:
    fraction, source = _fraction(params, signal)
    if fraction is None:
        return result.out("unsupported", source, f"{label}: {source}")
    try:
        equity = Decimal(str(balance["balance"])) + Decimal(str(balance["pnl"]))
    except (KeyError, TypeError, InvalidOperation):
        return result.out("unknown", f"get_balance answered without balance and pnl: {balance}", f"{label}: balance unreadable")
    deposit = equity * fraction
    sizing: dict[str, Any] = {"equity": str(equity), "fraction": str(fraction), "source": source, "deposit": str(deposit)}
    result.extra["sizing"] = sizing

    price = await _price(ctx, params.symbol)
    if price is None:
        return result.out("unknown", "no last price for the size", f"{label}: no price to size from")
    sized = await ctx.call("size_for_margin", {"symbol": params.symbol, "margin": float(deposit), "price": price})
    if not sized.ok:
        return result.out("refused", sized.text, f"{label}: size refused — {sized.text}")
    size = (_payload(sized.text) or {}).get("size")
    sizing["size"] = size
    if not isinstance(size, int | float) or size <= 0:
        return result.out("refused", f"size_for_margin answered no usable size: {sized.text}", f"{label}: no size")

    direction = _DIRECTION[action.side or ""]
    arguments = {"symbol": params.symbol, "direction": direction, "size": size, "order_type": "MARKET"}
    result.mark("order_sent", now())
    try:
        outcome = await ctx.call("place_order", arguments, attempt_key=attempt_key)
    except AttemptAlreadyMade:
        return result.out("skipped", "an entry on this signal bar was already attempted", f"{label}: entry already attempted")
    result.mark("order_answered", now())
    if outcome.settles_as_refused:
        return result.out("refused", outcome.text, f"{label}: {direction} {size} refused — {outcome.text}")
    order = _payload(outcome.text) if outcome.ok else None
    result.extra["order"] = order if outcome.ok else outcome.text
    if not _settled(order) or order.get("id") is None:
        return result.out("unknown", outcome.text, f"{label}: {direction} {size} has no known outcome — check the account")

    level = order.get("level")
    assumed = await _assumed_open(ctx, params.symbol, signal.get("bar_closed_at"))
    if assumed is not None and isinstance(level, int | float):
        sign = 1 if direction == "BUY" else -1
        result.extra["vs_backtest"] = {
            "assumed_open": assumed,
            "slippage_points": round((level - assumed) * sign, 2),
        }
    return result.out(
        "entered",
        None,
        f"{label}: {direction} {size} filled at {level}, position {order.get('id')} ({source} deposit {fraction})",
    )


def _fraction(params: StrategyExecuteParams, signal: dict[str, Any]) -> tuple[Decimal | None, str]:
    if params.deposit_fraction is not None:
        return Decimal(params.deposit_fraction), "step"
    sizing = signal.get("sizing") or {}
    if sizing.get("mode") != "margin_fraction":
        return None, (
            f"the strategy sizes by {sizing.get('mode')!r}; this recipe sizes by deposit — set deposit_fraction on the step"
        )
    return Decimal(str(sizing.get("value"))), "document"


async def _price(ctx, symbol: str) -> float | None:
    outcome = await ctx.call("get_last_price", {"symbol": symbol, "resolution": "MINUTE"})
    close = (_payload(outcome.text) or {}).get("close") if outcome.ok else None
    return float(close) if isinstance(close, int | float) else None


async def _assumed_open(ctx, symbol: str, bar_closed_at: str | None) -> float | None:
    """The open of the minute the backtest would have filled in — the one starting when the signal bar closed."""
    if bar_closed_at is None:
        return None
    start = _iso(bar_closed_at)
    outcome = await ctx.call(
        "get_candles",
        {
            "symbol": symbol,
            "resolution": "MINUTE",
            "from_iso": start.isoformat(),
            "to_iso": (start + timedelta(minutes=1)).isoformat(),
        },
    )
    candles = (_payload(outcome.text) or {}).get("candles") if outcome.ok else None
    first = next((c for c in candles or [] if _iso(str(c.get("time"))) == start), None)
    return float(first["open"]) if first is not None else None
