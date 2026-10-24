"""The document a strategy is: its shape, and every check that can be made before it is saved. What the archive holds is
the one fact from outside, handed in as `available` so this module never does I/O."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from . import formula as f
from .checking import (
    ParamDecl,
    Scope,
    check,
    children,
    infer,
    let_order,
    names_used,
    reserved_problem,
)
from .problems import Problem
from .vocabulary import DERIVED_FROM_MINUTE, FUNCTIONS, RESOLUTIONS, SERIES, Indicator, Place, Type

# The language a document is written in. Raised only when the meaning of something already accepted changes; an
# addition (a new function, a new optional field) keeps it, so every saved document stays runnable.
SCHEMA_VERSION = 1

Resolution = Literal["MINUTE", "MINUTE_5", "MINUTE_15", "MINUTE_30", "HOUR", "HOUR_4", "DAY", "WEEK"]
_Formula = Annotated[str, Field(min_length=1)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ParamIn(_Strict):
    default: float
    min: float
    max: float
    step: float = Field(gt=0)


class OrderIn(_Strict):
    type: Literal["market", "limit", "stop"] = "market"
    price: _Formula | None = None
    expires_bars: int | None = Field(default=None, ge=1, le=5000)


class EntryIn(_Strict):
    side: Literal["long", "short"]
    when: _Formula
    order: OrderIn = Field(default_factory=OrderIn)


class TrailIn(_Strict):
    after_r: float = Field(gt=0)
    distance: _Formula


class ExitsIn(_Strict):
    stop: _Formula
    target: _Formula | None = None
    trail: TrailIn | None = None
    when: _Formula | None = None
    max_bars: int | None = Field(default=None, ge=1, le=100_000)


class SizingIn(_Strict):
    mode: Literal["risk_fraction", "fixed_units"]
    value: float = Field(gt=0)


class LimitsIn(_Strict):
    daily_stop_r: float | None = Field(default=None, lt=0)
    no_entry: _Formula | None = None


class DocumentIn(_Strict):
    schema_: int = Field(alias="schema", ge=1)
    name: str = Field(min_length=1, max_length=200)
    hypothesis: str = Field(default="", max_length=4000)
    notes: str = Field(default="", max_length=8000)
    symbol: str = Field(min_length=1, max_length=64)
    timeframe: Resolution
    params: dict[str, ParamIn] = Field(default_factory=dict)
    let: dict[str, _Formula] = Field(default_factory=dict)
    entries: list[EntryIn] = Field(min_length=1, max_length=20)
    exits: ExitsIn
    sizing: SizingIn
    limits: LimitsIn = Field(default_factory=LimitsIn)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    def canonical(self) -> dict[str, Any]:
        """The document as stored: defaults filled, keys in one order, so the same strategy written twice is one hash."""
        return self.model_dump(mode="json", by_alias=True)


def content_hash(document: Mapping[str, Any]) -> str:
    text = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Checked:
    """A document that passed: its canonical form, its parsed formulas by path, and the type each `let` gives."""

    document: DocumentIn
    formulas: Mapping[str, f.Node]
    let_types: Mapping[str, Type]
    let_order: tuple[str, ...]

    @property
    def canonical(self) -> dict[str, Any]:
        return self.document.canonical()

    @property
    def hash(self) -> str:
        return content_hash(self.canonical)


def validate(
    raw: Any,
    catalogue: Mapping[str, Indicator],
    available: set[tuple[str, str]] | None,
) -> tuple[Checked | None, list[Problem]]:
    """Every problem with `raw`, or the checked document. `available` is the archive's (symbol, resolution) pairs it can
    serve; `None` when the archive could not be asked, which is itself a problem the caller reports."""
    if isinstance(raw, Mapping) and isinstance(raw.get("schema"), int) and raw["schema"] > SCHEMA_VERSION:
        return None, [Problem(
            "schema", f"this document is written for schema {raw['schema']}; this engine reads up to {SCHEMA_VERSION}",
        )]
    try:
        document = DocumentIn.model_validate(raw)
    except ValidationError as err:
        return None, [_from_pydantic(e) for e in err.errors()]

    problems: list[Problem] = []
    params = _params(document, problems)
    parsed: dict[str, f.Node] = {}
    for path, text in _formula_fields(document):
        node, found = f.parse(text, path)
        problems.extend(found)
        if node is not None:
            parsed[path] = node

    let_types: dict[str, Type] = {}
    references = {}
    for name in document.let:
        path = f"let.{name}"
        clash = reserved_problem(name, path, catalogue)
        if clash is not None:
            problems.append(clash)
        references[name] = names_used(parsed[path]) if path in parsed else set()
    order, unordered = let_order(references)
    for name in unordered:
        problems.append(Problem(f"let.{name}", f"`{name}` is defined through itself, or through a variable that is"))
    for name in order:
        path = f"let.{name}"
        if path not in parsed:
            continue
        scope = Scope(Place.LET, params, dict(let_types), catalogue)
        found_type, found = infer(parsed[path], scope, path)
        problems.extend(found)
        if found_type is not None:
            let_types[name] = found_type

    for path, place, expected in _typed_fields(document):
        if path in parsed:
            problems.extend(check(parsed[path], Scope(place, params, let_types, catalogue), path, expected))

    problems.extend(_orders(document))
    if available is not None:
        problems.extend(_archive(document, parsed, available))
    if problems:
        return None, problems
    return Checked(document, parsed, let_types, tuple(order)), []


def _from_pydantic(error: Mapping[str, Any]) -> Problem:
    path = ".".join(str(part) if not isinstance(part, int) else f"[{part}]" for part in error["loc"]).replace(".[", "[")
    if error["type"] == "extra_forbidden":
        return Problem(path, f"`{error['loc'][-1]}` is not a field of a strategy document here")
    if error["type"] == "missing" and path == "exits.stop":
        return Problem(path, "a strategy needs a stop: it is what 1 R measures")
    return Problem(path or "document", error["msg"])


def _params(document: DocumentIn, problems: list[Problem]) -> dict[str, ParamDecl]:
    declared: dict[str, ParamDecl] = {}
    for name, p in document.params.items():
        path = f"params.{name}"
        if not name.isidentifier():
            problems.append(Problem(path, f"`{name}` cannot name a parameter; it is read as p.{name}"))
            continue
        if not p.min <= p.default <= p.max:
            problems.append(Problem(path, f"the default {p.default:g} is outside {p.min:g} to {p.max:g}"))
        # Declared even when its default is wrong, so every formula using it is not refused a second time for it.
        declared[name] = ParamDecl(p.default, p.min, p.max, p.step)
    return declared


def _formula_fields(d: DocumentIn) -> Iterator[tuple[str, str]]:
    for name, text in d.let.items():
        yield f"let.{name}", text
    for path, _, _ in _typed_fields(d):
        yield path, _text(d, path)


def _typed_fields(d: DocumentIn) -> Iterator[tuple[str, Place, Type]]:
    for i, entry in enumerate(d.entries):
        yield f"entries[{i}].when", Place.ENTRY, Type.CONDITION
        if entry.order.price is not None:
            yield f"entries[{i}].order.price", Place.ENTRY, Type.NUMBER
    yield "exits.stop", Place.EXIT, Type.NUMBER
    if d.exits.target is not None:
        yield "exits.target", Place.EXIT, Type.NUMBER
    if d.exits.trail is not None:
        yield "exits.trail.distance", Place.EXIT, Type.NUMBER
    if d.exits.when is not None:
        yield "exits.when", Place.EXIT, Type.CONDITION
    if d.limits.no_entry is not None:
        yield "limits.no_entry", Place.LIMIT, Type.CONDITION


def _text(d: DocumentIn, path: str) -> str:
    if path.startswith("entries["):
        index = int(path[len("entries["):path.index("]")])
        entry = d.entries[index]
        return entry.when if path.endswith(".when") else entry.order.price or ""
    return {
        "exits.stop": d.exits.stop,
        "exits.target": d.exits.target,
        "exits.trail.distance": d.exits.trail.distance if d.exits.trail else None,
        "exits.when": d.exits.when,
        "limits.no_entry": d.limits.no_entry,
    }[path] or ""


def _orders(d: DocumentIn) -> list[Problem]:
    problems = []
    for i, entry in enumerate(d.entries):
        path = f"entries[{i}].order"
        if entry.order.type == "market" and entry.order.price is not None:
            problems.append(Problem(f"{path}.price", "a market order fills at the next price; it takes no price"))
        if entry.order.type != "market" and entry.order.price is None:
            problems.append(Problem(f"{path}.price", f"a {entry.order.type} order needs a price formula"))
    return problems


def contexts(d: DocumentIn, parsed: Mapping[str, f.Node]) -> set[tuple[str, str]]:
    """Every (instrument, resolution) a document reads, the traded one at its timeframe and at `MINUTE` included."""
    found = {(d.symbol, d.timeframe), (d.symbol, "MINUTE")}

    def walk(n: f.Node, symbol: str, resolution: str) -> None:
        # Recorded where a series is read rather than at each `@`: `x @ US500 @ DAY` reads US500 at DAY, never US100 at DAY.
        if isinstance(n, f.Name) and n.id in SERIES or isinstance(n, f.Call) and n.function not in FUNCTIONS:
            found.add((symbol, resolution))
        if isinstance(n, f.At):
            if n.context in RESOLUTIONS:
                resolution = n.context
            else:
                symbol = n.context
        for child in children(n):
            walk(child, symbol, resolution)

    for node in parsed.values():
        walk(node, d.symbol, d.timeframe)
    return found


def _archive(d: DocumentIn, parsed: Mapping[str, f.Node], available: set[tuple[str, str]]) -> list[Problem]:
    problems = []
    if (d.symbol, "MINUTE") not in available:
        problems.append(Problem(
            "symbol", f"the archive does not collect {d.symbol} at MINUTE, and fills are settled on minutes",
            hint="start collecting it in the terminal's data manager",
        ))
    for symbol, resolution in sorted(contexts(d, parsed)):
        if (symbol, resolution) in available or (symbol, resolution) == (d.symbol, "MINUTE"):
            continue
        problems.append(Problem(
            "document", f"the archive cannot serve {symbol} at {resolution}, which this document reads",
        ))
    return problems


def servable(tracked: set[tuple[str, str]]) -> set[tuple[str, str]]:
    """What the archive can answer for: each pair it collects, and the resolutions it derives from a collected minute."""
    derived = {(symbol, res) for symbol, collected in tracked if collected == "MINUTE" for res in DERIVED_FROM_MINUTE}
    return tracked | derived
