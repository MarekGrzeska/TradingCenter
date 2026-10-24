"""The document a strategy is: its shape, and every check that can be made before it is saved. What the archive holds is
the one fact from outside, handed in as `available` so this module never does I/O."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from functools import cached_property
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
    through_at,
    unreadable_name,
)
from .problems import Problem
from .vocabulary import (
    DERIVED_FROM_MINUTE,
    FUNCTIONS,
    SERIES,
    TIME,
    Indicator,
    Place,
    Type,
)

# The language a document is written in. Raised only when the meaning of something already accepted changes; an
# addition (a new function, a new optional field) keeps it, so every saved document stays runnable.
SCHEMA_VERSION = 1

Resolution = Literal["MINUTE", "MINUTE_5", "MINUTE_15", "MINUTE_30", "HOUR", "HOUR_4", "DAY", "WEEK"]
_Formula = Annotated[str, Field(min_length=1)]


class _Strict(BaseModel):
    # No infinities: they pass a range check and then cannot be stored, since jsonb has no Infinity.
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


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

    model_config = ConfigDict(extra="forbid", populate_by_name=True, allow_inf_nan=False)

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

    @cached_property
    def canonical(self) -> dict[str, Any]:
        return self.document.canonical()

    @cached_property
    def hash(self) -> str:
        return content_hash(self.canonical)


def validate(
    raw: Any,
    catalogue: Mapping[str, Indicator],
    available: set[tuple[str, str]],
) -> tuple[Checked | None, list[Problem]]:
    """Every problem with `raw`, or the checked document. `available` is the (symbol, resolution) pairs the archive can
    serve — required, because a document nobody checked against the archive is not a valid one."""
    try:
        document = DocumentIn.model_validate(raw)
    except ValidationError as err:
        return None, [_from_pydantic(e) for e in err.errors()]
    if document.schema_ > SCHEMA_VERSION:
        return None, [Problem(
            "schema", f"this document is written for schema {document.schema_}; this engine reads up to {SCHEMA_VERSION}",
        )]

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
    # Declared, but without a type to give: already refused where it is defined, so silent where it is used.
    untyped = set(document.let)
    for name in order:
        path = f"let.{name}"
        if path not in parsed:
            continue
        scope = Scope(Place.LET, params, dict(let_types), catalogue, frozenset(untyped - set(let_types)))
        found_type, found = infer(parsed[path], scope, path)
        problems.extend(found)
        if found_type is not None:
            let_types[name] = found_type
    untyped -= set(let_types)

    for path, place, expected, _ in _typed_fields(document):
        if path in parsed:
            scope = Scope(place, params, let_types, catalogue, frozenset(untyped))
            problems.extend(check(parsed[path], scope, path, expected))

    problems.extend(_orders(document))
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
        if unreadable_name(name):
            problems.append(Problem(path, f"`{name}` cannot name a parameter: no formula could read it as p.{name}"))
            continue
        if not p.min <= p.default <= p.max:
            problems.append(Problem(path, f"the default {p.default:g} is outside {p.min:g} to {p.max:g}"))
        # Declared even when its default is wrong, so every formula using it is not refused a second time for it.
        declared[name] = ParamDecl(p.default, p.min, p.max, p.step)
    return declared


def _formula_fields(d: DocumentIn) -> Iterator[tuple[str, str]]:
    for name, text in d.let.items():
        yield f"let.{name}", text
    for path, _, _, text in _typed_fields(d):
        yield path, text


def _typed_fields(d: DocumentIn) -> Iterator[tuple[str, Place, Type, str]]:
    """Every formula outside `let`: where it is, what may stand there, what it must give, and its text."""
    for i, entry in enumerate(d.entries):
        yield f"entries[{i}].when", Place.ENTRY, Type.CONDITION, entry.when
        if entry.order.price is not None:
            yield f"entries[{i}].order.price", Place.ENTRY, Type.NUMBER, entry.order.price
    yield "exits.stop", Place.EXIT, Type.NUMBER, d.exits.stop
    if d.exits.target is not None:
        yield "exits.target", Place.EXIT, Type.NUMBER, d.exits.target
    if d.exits.trail is not None:
        yield "exits.trail.distance", Place.EXIT, Type.NUMBER, d.exits.trail.distance
    if d.exits.when is not None:
        yield "exits.when", Place.EXIT, Type.CONDITION, d.exits.when
    if d.limits.no_entry is not None:
        yield "limits.no_entry", Place.LIMIT, Type.CONDITION, d.limits.no_entry


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

    def walk(n: f.Node, ctx: tuple[str, str]) -> None:
        # Recorded where bars are read: each series name, each indicator, and the axis every chain of `@` is read on —
        # so `x @ US500 @ DAY` reads US500 at DAY, and never US100 at DAY.
        reads_bars = isinstance(n, f.Name) and (n.id in SERIES or n.id in TIME)
        if reads_bars or isinstance(n, f.Call) and n.function not in FUNCTIONS:
            found.add(ctx)
        if isinstance(n, f.At):
            value, inner = through_at(n, ctx)
            found.add(inner)
            walk(value, inner)
            return
        for child in children(n):
            walk(child, ctx)

    for node in parsed.values():
        walk(node, (d.symbol, d.timeframe))
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
