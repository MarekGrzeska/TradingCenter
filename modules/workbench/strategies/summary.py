"""A document read back in Polish, from the document alone: no model and no knowledge of the sentence it was written from,
so a strategy the agent misunderstood reads as the strategy it is (`strategies-documents`, design D4). Deterministic —
the same document is the same summary — and literal wherever a construction has no phrase."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from . import formula as f
from .document import DocumentIn
from .vocabulary import FUNCTIONS, NAME_PHRASES, RESOLUTIONS

# The terminal's names for the archive's resolutions (`terminal-shell`): the summary is read on the screen.
TERMINAL_NAMES: dict[str, str] = {
    "MINUTE": "m1", "MINUTE_5": "m5", "MINUTE_15": "m15", "MINUTE_30": "m30",
    "HOUR": "h1", "HOUR_4": "h4", "DAY": "day", "WEEK": "week",
}

_COMPARE = {">": "powyżej", "<": "poniżej", ">=": "co najmniej", "<=": "co najwyżej", "==": "równe", "!=": "różne od"}
_ARITH = {"+": "+", "-": "−", "*": "×", "/": "/"}
_SIDES = {"long": "Long", "short": "Short"}
_ON_DAY = {
    "MONDAY": "w poniedziałek", "TUESDAY": "we wtorek", "WEDNESDAY": "w środę", "THURSDAY": "w czwartek",
    "FRIDAY": "w piątek", "SATURDAY": "w sobotę", "SUNDAY": "w niedzielę",
}


def summarize(raw: Mapping[str, Any]) -> dict[str, Any] | None:
    """The summary of a document that has the shape of one, or `None`. Formulas are parsed here, not taken from a check,
    so a stored revision is summarised without asking the archive anything."""
    try:
        d = DocumentIn.model_validate(raw)
    except ValidationError:
        return None

    def say(text: str | None, path: str) -> str:
        if text is None:
            return ""
        node, _ = f.parse(text, path)
        return text if node is None else _formula(node)

    sections: list[dict[str, Any]] = [
        {"title": "Instrument", "lines": [f"{d.symbol}, decyzje na zamknięciu świecy {TERMINAL_NAMES[d.timeframe]}."]},
    ]
    if d.params:
        sections.append({"title": "Parametry", "lines": [
            f"p.{name}: domyślnie {_number(p.default)}, od {_number(p.min)} do {_number(p.max)} co {_number(p.step)}."
            for name, p in d.params.items()
        ]})
    if d.let:
        sections.append({"title": "Zmienne", "lines": [
            f"«{name}» = {say(text, f'let.{name}')}." for name, text in d.let.items()
        ]})
    entries = []
    for i, entry in enumerate(d.entries):
        line = f"{_SIDES[entry.side]}, gdy {say(entry.when, f'entries[{i}].when')}."
        order = entry.order
        if order.type == "market":
            line += " Zlecenie rynkowe po zamknięciu świecy."
        else:
            kind = "z limitem" if order.type == "limit" else "stop"
            line += f" Zlecenie {kind} po cenie {say(order.price, f'entries[{i}].order.price')}"
            line += f", ważne {_bars(order.expires_bars)}." if order.expires_bars else ", ważne do odwołania."
        entries.append(line)
    sections.append({"title": "Wejścia", "lines": entries})

    exits = [f"Stop: {say(d.exits.stop, 'exits.stop')}."]
    if d.exits.target is not None:
        exits.append(f"Cel: {say(d.exits.target, 'exits.target')}.")
    if d.exits.trail is not None:
        exits.append(
            f"Stop kroczący od {_number(d.exits.trail.after_r)} R zysku, w odległości "
            f"{say(d.exits.trail.distance, 'exits.trail.distance')}."
        )
    if d.exits.when is not None:
        exits.append(f"Wyjście, gdy {say(d.exits.when, 'exits.when')}.")
    if d.exits.max_bars is not None:
        exits.append(f"Najwyżej {_bars(d.exits.max_bars)} w pozycji.")
    sections.append({"title": "Wyjścia", "lines": exits})

    if d.sizing.mode == "risk_fraction":
        sizing = f"Ryzyko {_number(d.sizing.value * 100)}% kapitału na transakcję (odległość do stopu = 1 R)."
    else:
        sizing = f"Stała wielkość: {_number(d.sizing.value)} jednostek."
    sections.append({"title": "Rozmiar", "lines": [sizing]})

    limits = []
    if d.limits.daily_stop_r is not None:
        limits.append(f"Bez nowych wejść tego dnia (UTC) po wyniku {_number(d.limits.daily_stop_r)} R.")
    if d.limits.no_entry is not None:
        limits.append(f"Bez wejść, gdy {say(d.limits.no_entry, 'limits.no_entry')}.")
    if limits:
        sections.append({"title": "Limity", "lines": limits})

    return {"name": d.name, "sections": sections, "hypothesis": d.hypothesis, "notes": d.notes}


def _number(value: float) -> str:
    text = f"{value:g}" if abs(value) < 1e15 else repr(value)
    return text.replace("-", "−").replace(".", ",")


def _bars(n: int) -> str:
    if n == 1:
        return "1 świeca"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return f"{n} świece"
    return f"{n} świec"


def _window(n: f.Node) -> str:
    """A window's length as a count of bars: `z 20 świec`, or a parameter's name."""
    if isinstance(n, f.Num) and n.value == int(n.value):
        count = int(n.value)
        return "1 świecy" if count == 1 else f"{count} świec"
    return f"{_formula(n)} świec"


def _hour(h: float, op: str) -> str:
    """An hour of the language — always UTC — with the hours it is in Poland, winter and summer."""
    start = int(h) + (1 if op in (">", "<=") else 0)
    word = {">=": "od", ">": "od", "<": "przed", "<=": "przed", "==": "w godzinie", "!=": "poza godziną"}[op]
    return f"{word} {start % 24}:00 UTC, czyli {(start + 1) % 24}:00 zimą i {(start + 2) % 24}:00 latem w Polsce"


def _flip(op: str) -> str:
    return {">": "<", "<": ">", ">=": "<=", "<=": ">="}.get(op, op)


def _comparison(op: str, left: f.Node, right: f.Node) -> str:
    if isinstance(left, f.Name) and left.id == "hour" and isinstance(right, f.Num):
        return _hour(right.value, op)
    if isinstance(right, f.Name) and right.id == "hour" and isinstance(left, f.Num):
        return _hour(left.value, _flip(op))
    if isinstance(left, f.Name) and left.id == "weekday" and isinstance(right, f.Name) and op in ("==", "!="):
        day = _ON_DAY.get(right.id, f"w {_formula(right)}")
        return day if op == "==" else f"nie {day}"
    return f"{_formula(left)} {_COMPARE[op]} {_formula(right)}"


def _grouped(n: f.Node) -> str:
    text = _formula(n)
    return f"({text})" if isinstance(n, f.Arith | f.Logic | f.IfElse | f.Compare) else text


_PRECEDENCE = {"+": 1, "-": 1, "*": 2, "/": 2}


def _operand(n: f.Node, parent: str, right: bool) -> str:
    """An operand of + − × /, in parentheses only where reading it without them would change the arithmetic."""
    if isinstance(n, f.Arith):
        lower = _PRECEDENCE[n.op] < _PRECEDENCE[parent]
        same_but_not_associative = right and _PRECEDENCE[n.op] == _PRECEDENCE[parent] and parent in "-/"
        return f"({_formula(n)})" if lower or same_but_not_associative else _formula(n)
    return _grouped(n)


def _formula(n: f.Node) -> str:
    if isinstance(n, f.Num):
        return _number(n.value)
    if isinstance(n, f.Bool):
        return "prawda" if n.value else "fałsz"
    if isinstance(n, f.Name):
        if n.id in NAME_PHRASES:
            return NAME_PHRASES[n.id]
        if n.id in RESOLUTIONS:
            return TERMINAL_NAMES[n.id]
        return f"«{n.id}»"
    if isinstance(n, f.Param):
        return f"p.{n.name}"
    if isinstance(n, f.Neg):
        return f"−{_grouped(n.operand)}"
    if isinstance(n, f.Arith):
        return f"{_operand(n.left, n.op, False)} {_ARITH[n.op]} {_operand(n.right, n.op, True)}"
    if isinstance(n, f.Compare):
        parts = [_comparison(op, n.operands[i], n.operands[i + 1]) for i, op in enumerate(n.ops)]
        return " i ".join(parts)
    if isinstance(n, f.Logic):
        joiner = " i " if n.op == "and" else " lub "
        return joiner.join(
            f"({_formula(v)})" if isinstance(v, f.Logic) and v.op != n.op else _formula(v) for v in n.values
        )
    if isinstance(n, f.Not):
        return f"nie ({_formula(n.operand)})"
    if isinstance(n, f.IfElse):
        return f"{_formula(n.then)}, gdy {_formula(n.condition)}, a w przeciwnym razie {_formula(n.otherwise)}"
    if isinstance(n, f.Call):
        return _call(n)
    if isinstance(n, f.Field):
        return f"{_formula(n.value)}, linia {n.name}"
    if isinstance(n, f.Lag):
        bars = n.bars
        if isinstance(bars, f.Param):
            return f"{_grouped(n.value)} sprzed p.{bars.name} świec"
        if bars == 0:
            return _formula(n.value)
        return f"{_grouped(n.value)} sprzed {'1 świecy' if bars == 1 else f'{bars} świec'}"
    if isinstance(n, f.At):
        contexts = [n.context]
        inner = n.value
        while isinstance(inner, f.At):
            contexts.insert(0, inner.context)
            inner = inner.value
        named = ", ".join(TERMINAL_NAMES.get(c, c) for c in contexts)
        return f"{_grouped(inner)} na {named}"
    return "…"


def _call(n: f.Call) -> str:
    fn = FUNCTIONS.get(n.function)
    if fn is None:
        # Not the language's own, so the archive's catalogue — the check at save time saw to that.
        args = [_formula(a) for a in n.args] + [f"{k} {_formula(v)}" for k, v in n.kwargs]
        return f"{n.function.upper()}({', '.join(args)})"
    said = []
    for i, arg in enumerate(n.args):
        kind = fn.args[min(i, len(fn.args) - 1)]
        said.append(_window(arg) if kind.value == "window" else _formula(arg))
    if not fn.phrase:
        return f"{n.function}({', '.join(said)})"
    return fn.phrase.format(*said, all=", ".join(said))
