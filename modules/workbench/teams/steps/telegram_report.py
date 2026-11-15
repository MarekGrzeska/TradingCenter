"""`telegram_report`: the result of the `strategy_execute` before it, told on Telegram in one fixed shape, by no model. What
to say is `compose`, tested as a table; the recipe around it only finds the result and sends the text."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from ..contract import StepDefinition
from .catalogue import TelegramReportParams
from .runtime_types import StepContext

NOTICE_TOOL = "send_telegram_message"
MISSING = "niedostępne"
_WARSAW = ZoneInfo("Europe/Warsaw")

_HEADLINE = {
    "entered": "WEJŚCIE",
    "exited": "WYJŚCIE",
    "refused": "ODRZUCONE",
    "unknown": "ALERT TECHNICZNY — wynik nieznany, sprawdź konto ręcznie",
    "unsupported": "NIEOBSŁUGIWANE",
    "skipped": "POMINIĘTE",
}


def _execution_result(given: Sequence[tuple[str, str]]) -> dict[str, Any] | None:
    """The last predecessor whose work is a strategy step's result; an agent's prose is not one."""
    for _key, output in reversed(given):
        try:
            data = json.loads(output)
        except (TypeError, ValueError):
            continue
        if isinstance(data, dict) and "decision" in data:
            return data
    return None


def _part(data: dict[str, Any], name: str) -> dict[str, Any]:
    value = data.get(name)
    return value if isinstance(value, dict) else {}


def _value(value: Any) -> str:
    if value is None or value == "":
        return MISSING
    return str(value)


def _signed(value: Any, unit: str = "") -> str:
    if not isinstance(value, int | float) or isinstance(value, bool):
        return MISSING
    text = f"{value:+.2f}"
    return f"{text} {unit}".strip()


def _bar(signal: dict[str, Any]) -> str:
    closed = signal.get("bar_closed_at")
    if not isinstance(closed, str):
        return MISSING
    try:
        local = datetime.fromisoformat(closed).astimezone(_WARSAW)
    except ValueError:
        return closed
    age = signal.get("bar_age_seconds")
    suffix = f", wiek {int(age)} s" if isinstance(age, int | float) and not isinstance(age, bool) else ""
    return f"{local:%d.%m %H:%M} (Warszawa){suffix}"


def compose(result: dict[str, Any] | None, prefix: str | None) -> str | None:
    """The message for one step result, or None where there is nothing to tell: no action, or a repeat of a bar already
    acted on. Every field the result does not carry is written as missing, never estimated."""
    lines = [prefix.strip()] if prefix and prefix.strip() else []
    if result is None:
        return "\n".join([*lines, "ALERT TECHNICZNY — brak wyniku kroku strategii, sprawdź przebieg"])
    decision = result.get("decision")
    if decision == "no_action" or (decision == "skipped" and result.get("same_bar")):
        return None
    signal = _part(result, "signal")
    trade = _part(result, "trade")
    order = _part(signal, "order")
    engine = _part(signal, "position")
    side = trade.get("side") or order.get("side") or engine.get("side")
    headline = _HEADLINE.get(str(decision), f"ALERT TECHNICZNY — decyzja {decision!r}")
    lines.append(f"{headline} · {result.get('symbol') or MISSING} · {str(side).upper() if side else MISSING}")

    if decision == "entered":
        lines.append(f"Cena wykonania: {_value(trade.get('fill_price'))}")
        lines.append(f"Wielkość: {_value(trade.get('size'))} · pozycja {_value(trade.get('position_id'))}")
        vs = _part(result, "vs_backtest")
        if vs:
            lines.append(
                f"Wobec backtestu: {_signed(vs.get('slippage_points'), 'pkt')} (zakładał {_value(vs.get('assumed_open'))})"
            )
        sizing = _part(result, "sizing")
        if sizing:
            lines.append(f"Depozyt: {_value(sizing.get('fraction'))} z equity {_value(sizing.get('equity'))}")
    elif decision == "exited":
        currency = trade.get("currency") or ""
        pnl = _signed(trade.get("pnl"), currency)
        if trade.get("pnl_approximate") and pnl != MISSING:
            pnl = f"około {pnl} (niezrealizowany tuż przed zamknięciem)"
        lines.append(f"Cena otwarcia: {_value(trade.get('open_price'))}")
        lines.append(f"Cena zamknięcia: {_value(trade.get('close_price'))} ({_signed(trade.get('points'), 'pkt')})")
        lines.append(f"Wielkość: {_value(trade.get('size'))} · pozycja {_value(result.get('position_id'))}")
        lines.append(f"Wynik: {pnl}")
    if result.get("reason"):
        lines.append(f"Powód: {result['reason']}")
    lines.append(f"Świeca sygnału: {_bar(signal)}")
    return "\n".join(lines)


async def execute(step: StepDefinition, ctx: StepContext, given: Sequence[tuple[str, str]]) -> dict[str, Any]:
    params = TelegramReportParams.model_validate(step.params)
    text = compose(_execution_result(given), params.prefix)
    if text is None:
        return {"sent": False, "reason": "nothing to tell", "summary": "telegram: nothing to tell"}
    arguments: dict[str, Any] = {"destination": params.destination, "text": text}
    if params.bot is not None:
        arguments["bot"] = params.bot
    outcome = await ctx.call(NOTICE_TOOL, arguments)
    if not outcome.ok:
        return {"sent": False, "reason": outcome.text, "text": text, "summary": f"telegram: not sent — {outcome.text}"}
    return {"sent": True, "reason": None, "text": text, "summary": "telegram: sent"}
