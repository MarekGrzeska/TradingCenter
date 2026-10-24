"""Names and types: whether a parsed formula means something, in the place of the document it stands. Every problem is
collected rather than the first one raised, because a model fixing a document in a loop needs the whole list at once."""

from __future__ import annotations

import difflib
import keyword
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field

from . import formula as f
from .problems import Problem
from .vocabulary import (
    CONSTANTS,
    FUNCTIONS,
    HISTORY,
    MAX_BARS,
    PER_BAR,
    POSITION,
    RESERVED,
    RESOLUTIONS,
    SERIES,
    TIME,
    Arg,
    Indicator,
    Place,
    Type,
    inner_context,
)


@dataclass(frozen=True)
class ParamDecl:
    default: float
    min: float
    max: float
    step: float

    @property
    def integer(self) -> bool:
        return all(float(v).is_integer() for v in (self.default, self.min, self.max, self.step))


@dataclass(frozen=True)
class Scope:
    place: Place
    params: Mapping[str, ParamDecl]
    lets: Mapping[str, Type]
    catalogue: Mapping[str, Indicator]
    # Variables declared but refused where they are defined; reading one is not a second defect.
    untyped_lets: frozenset[str] = frozenset()


@dataclass
class _Context:
    """Where the walk is: inside how many `@`, and which of the two kinds each named."""

    symbol: str | None = None
    resolution: str | None = None
    # Inside an offset or a function over bars: a series of past values, which the trade's state is not — it exists
    # one bar at a time, while the engine walks.
    over_bars: bool = False

    @property
    def elsewhere(self) -> bool:
        return self.symbol is not None or self.resolution is not None


@dataclass
class _Walk:
    scope: Scope
    path: str
    problems: list[Problem] = field(default_factory=list)

    def refuse(self, node: f.Node, message: str, hint: str | None = None) -> None:
        self.problems.append(Problem(self.path, message, column=node.column, hint=hint))


def check(node: f.Node, scope: Scope, path: str, expected: Type) -> list[Problem]:
    """Every problem with `node` standing at `path`, where a value of type `expected` is wanted."""
    walk = _Walk(scope, path)
    found = _type(node, walk, _Context())
    if found is not None and found is not expected:
        walk.refuse(node, f"a {expected.value} is expected here, and this formula gives a {found.value}")
    return walk.problems


def infer(node: f.Node, scope: Scope, path: str) -> tuple[Type | None, list[Problem]]:
    """The type a `let` formula gives, and its problems — a variable may hold either a number or a condition."""
    walk = _Walk(scope, path)
    return _type(node, walk, _Context()), walk.problems


def let_order(references: Mapping[str, set[str]]) -> tuple[list[str], list[str]]:
    """The `let` names in an order where each comes after every name it uses, and the names that cannot be ordered —
    those in a cycle and those that use one. Kahn's algorithm, so no recursion however long the chain."""
    uses = {name: {u for u in used if u in references and u != name} for name, used in references.items()}
    selfish = {name for name, used in references.items() if name in used}
    users: dict[str, set[str]] = {name: set() for name in references}
    for name, used in uses.items():
        for u in used:
            users[u].add(name)
    waiting = {name: len(used) for name, used in uses.items()}
    ready = sorted(name for name, count in waiting.items() if count == 0 and name not in selfish)
    order: list[str] = []
    while ready:
        name = ready.pop(0)
        order.append(name)
        for user in sorted(users[name]):
            waiting[user] -= 1
            if waiting[user] == 0 and user not in selfish:
                ready.append(user)
        ready.sort()
    return order, sorted(set(references) - set(order))


def through_at(node: f.At, context: tuple[str, str]) -> tuple[f.Node, tuple[str, str]]:
    """A chain of `@` as one: `x @ US500 @ DAY` is `x` read in (US500, DAY), never through (traded, DAY), which nobody
    reads. Returns the first node that is not an `@`, and the context it is read in."""
    current: f.Node = node
    while isinstance(current, f.At):
        context = inner_context(context, current.context)
        current = current.value
    return current, context


def names_used(node: f.Node) -> set[str]:
    """Every bare name in a formula — what `let_order` reads its edges from."""
    found: set[str] = set()

    def walk(n: f.Node) -> None:
        if isinstance(n, f.Name):
            found.add(n.id)
        for child in children(n):
            walk(child)

    walk(node)
    return found


def children(n: f.Node) -> tuple[f.Node, ...]:
    if isinstance(n, f.Neg | f.Not):
        return (n.operand,)
    if isinstance(n, f.Arith):
        return (n.left, n.right)
    if isinstance(n, f.Compare):
        return n.operands
    if isinstance(n, f.Logic):
        return n.values
    if isinstance(n, f.IfElse):
        return (n.condition, n.then, n.otherwise)
    if isinstance(n, f.Call):
        return (*n.args, *(value for _, value in n.kwargs))
    if isinstance(n, f.Field | f.Lag | f.At):
        return (n.value,)
    return ()


def _type(n: f.Node, w: _Walk, ctx: _Context) -> Type | None:
    if isinstance(n, f.Num):
        return Type.NUMBER
    if isinstance(n, f.Bool):
        return Type.CONDITION
    if isinstance(n, f.Name):
        return _name(n, w, ctx)
    if isinstance(n, f.Param):
        return Type.NUMBER if _declared(n, w) is not None else None
    if isinstance(n, f.Neg | f.Arith):
        for child in children(n):
            _expect(child, Type.NUMBER, w, ctx, "arithmetic works on numbers")
        return Type.NUMBER
    if isinstance(n, f.Compare):
        for child in n.operands:
            _expect(child, Type.NUMBER, w, ctx, "a comparison compares numbers; join conditions with and / or")
        return Type.CONDITION
    if isinstance(n, f.Logic | f.Not):
        for child in children(n):
            _expect(child, Type.CONDITION, w, ctx, f"`{getattr(n, 'op', 'not')}` joins conditions")
        return Type.CONDITION
    if isinstance(n, f.IfElse):
        _expect(n.condition, Type.CONDITION, w, ctx, "the test of `a if test else b` is a condition")
        then, otherwise = _type(n.then, w, ctx), _type(n.otherwise, w, ctx)
        if then is not None and otherwise is not None and then is not otherwise:
            w.refuse(n, "both branches of `a if test else b` give the same type")
            return None
        return then or otherwise
    if isinstance(n, f.Lag):
        _bars(n, n.bars, w, minimum=0)
        return _type(n.value, w, _Context(ctx.symbol, ctx.resolution, over_bars=True))
    if isinstance(n, f.At):
        return _at(n, w, ctx)
    if isinstance(n, f.Field):
        if not isinstance(n.value, f.Call) or n.value.function not in w.scope.catalogue or n.value.function in FUNCTIONS:
            w.refuse(n, "a field is read only from an indicator of the catalogue that draws several lines")
            return None
        return _indicator(n.value, w, ctx, line=n.name, field_node=n)
    if isinstance(n, f.Call):
        if n.function in FUNCTIONS:
            return _function(n, w, ctx)
        if n.function in w.scope.catalogue:
            return _indicator(n, w, ctx, line=None, field_node=None)
        if n.function in SERIES or n.function in TIME or n.function in POSITION or n.function in HISTORY:
            w.refuse(n, f"`{n.function}` is a value, not a function; drop the parentheses")
            return None
        w.refuse(
            n, f"`{n.function}` is not a function of the language nor of the indicator catalogue",
            hint=_closest(n.function, [*FUNCTIONS, *w.scope.catalogue]),
        )
        return None
    w.refuse(n, "this is not part of the language")
    return None


def _expect(n: f.Node, expected: Type, w: _Walk, ctx: _Context, why: str) -> None:
    found = _type(n, w, ctx)
    if found is not None and found is not expected:
        w.refuse(n, f"a {expected.value} is expected here, and this gives a {found.value}: {why}")


def _name(n: f.Name, w: _Walk, ctx: _Context) -> Type | None:
    name, place = n.id, w.scope.place
    if name in SERIES or name in TIME:
        return Type.NUMBER
    if name in CONSTANTS:
        return Type.NUMBER
    if (name in POSITION or name in HISTORY) and ctx.over_bars and not ctx.elsewhere:
        w.refuse(n, f"`{name}` exists one bar at a time, so no offset or function over past bars can read it")
        return None
    if name in POSITION:
        if place is not Place.EXIT:
            w.refuse(n, f"`{name}` describes the open position, and before an entry there is none; it belongs in exits")
            return None
        if ctx.elsewhere:
            w.refuse(n, f"`{name}` is the traded position, and cannot be read under `@`")
            return None
        return Type.NUMBER
    if name in HISTORY:
        if place is Place.LET:
            w.refuse(
                n, f"`{name}` depends on trades, and a `let` is computed once for the whole range without them",
                hint="use it directly in entries, exits or limits",
            )
            return None
        if ctx.elsewhere:
            w.refuse(n, f"`{name}` is this strategy's own record, and cannot be read under `@`")
            return None
        return Type.NUMBER
    if name in RESOLUTIONS:
        w.refuse(n, f"`{name}` is a resolution; it stands only on the right of `@`", hint=f"close @ {name}")
        return None
    if name in w.scope.untyped_lets:
        return None
    if name in w.scope.lets:
        if ctx.elsewhere:
            w.refuse(n, "a `let` variable cannot be read under `@`; write its formula there instead")
            return None
        return w.scope.lets[name]
    if name in FUNCTIONS or name in w.scope.catalogue:
        w.refuse(n, f"`{name}` is a function and needs its arguments", hint=f"{name}(…)")
        return None
    known = [*SERIES, *TIME, *CONSTANTS, *POSITION, *HISTORY, *w.scope.lets]
    w.refuse(n, f"`{name}` is not a name the language knows", hint=_closest(name, known))
    return None


def _at(n: f.At, w: _Walk, ctx: _Context) -> Type | None:
    inner = _Context(ctx.symbol, ctx.resolution, over_bars=True)
    if n.context in RESOLUTIONS:
        if ctx.resolution is not None:
            w.refuse(n, "one formula reads one resolution under `@`; this one names two")
            return None
        inner.resolution = n.context
    else:
        # An instrument is any other name — but one a hair from a resolution, or a name of the language, is a slip.
        near = _closest(n.context.upper(), RESOLUTIONS)
        if n.context in RESERVED or (near is not None and _squeezed(n.context) == _squeezed(near)):
            w.refuse(n, f"`{n.context}` is neither a resolution nor an instrument", hint=near)
            return None
        if ctx.symbol is not None:
            w.refuse(n, "one formula reads one other instrument under `@`; this one names two")
            return None
        inner.symbol = n.context
    return _type(n.value, w, inner)


def _function(n: f.Call, w: _Walk, ctx: _Context) -> Type | None:
    spec = FUNCTIONS[n.function]
    if spec.places is not None and w.scope.place not in spec.places:
        w.refuse(n, f"`{n.function}` reads the open position, and before an entry there is none; it belongs in exits")
        return None
    if spec.name == "at_entry" and (ctx.elsewhere or ctx.over_bars):
        w.refuse(n, "`at_entry` is the traded position's bar; it cannot be read under `@`, an offset or a window")
        return None
    # Everything but plain arithmetic reads its arguments as series of past bars; `at_entry` reads one past bar.
    args_ctx = ctx if spec.name in PER_BAR else _Context(ctx.symbol, ctx.resolution, over_bars=True)
    if n.kwargs:
        w.refuse(n, f"`{n.function}` takes its arguments in order, not by name", hint=spec.signature())
        return None
    count = len(n.args)
    if count < len(spec.args) or (count > len(spec.args) and not spec.variadic):
        w.refuse(n, f"`{n.function}` takes {len(spec.args)}{' or more' if spec.variadic else ''} arguments", hint=spec.signature())
        return None
    for index, arg in enumerate(n.args):
        kind = spec.args[min(index, len(spec.args) - 1)]
        if kind is Arg.WINDOW:
            _window(arg, w)
        else:
            _expect(arg, Type(kind.value), w, args_ctx, f"argument {index + 1} of {spec.signature()}")
    return spec.returns


def _window(arg: f.Node, w: _Walk) -> None:
    if isinstance(arg, f.Num):
        if not arg.value.is_integer():
            w.refuse(arg, "a window is a whole number of bars")
        else:
            _bars(arg, int(arg.value), w, minimum=1)
    elif isinstance(arg, f.Param):
        _bars(arg, arg, w, minimum=1)
    else:
        w.refuse(arg, "a window is a whole number of bars or a parameter, never a formula", hint="highest(high, 20)")


def _bars(node: f.Node, bars: int | f.Param, w: _Walk, *, minimum: int) -> None:
    what = "an offset" if minimum == 0 else "a window"
    if isinstance(bars, int):
        if not minimum <= bars <= MAX_BARS:
            w.refuse(node, f"{what} is {minimum} to {MAX_BARS} bars; this one is {bars}")
        return
    decl = _declared(bars, w)
    if decl is None:
        return
    if not decl.integer or decl.min < minimum or decl.max > MAX_BARS:
        w.refuse(
            bars, f"p.{bars.name} is used as {what}, so it must be whole and stay within {minimum} to {MAX_BARS}",
        )


def _indicator(n: f.Call, w: _Walk, ctx: _Context, *, line: str | None, field_node: f.Field | None) -> Type | None:
    entry = w.scope.catalogue[n.function]
    if entry.output != "lines":
        w.refuse(
            n, f"`{n.function}` draws {entry.output}, not a line; only line indicators are values a formula can read",
        )
        return None
    if line is None and len(entry.lines) > 1:
        w.refuse(n, f"`{n.function}` draws several lines; choose one", hint=", ".join(f"{n.function}(…).{key}" for key in entry.lines))
        return None
    if line is not None and line not in entry.lines:
        w.refuse(field_node or n, f"`{n.function}` has no line `{line}`", hint=", ".join(entry.lines))
        return None

    by_name = {p.name: p for p in entry.params}
    given: dict[str, f.Node] = {}
    if len(n.args) > len(entry.params):
        w.refuse(n, f"`{n.function}` takes at most {len(entry.params)} parameters", hint=entry.signature())
        return None
    for param, arg in zip(entry.params, n.args, strict=False):
        given[param.name] = arg
    for name, arg in n.kwargs:
        if name not in by_name:
            w.refuse(arg, f"`{n.function}` has no parameter `{name}`", hint=_closest(name, by_name))
            continue
        if name in given:
            w.refuse(arg, f"`{name}` of `{n.function}` is given twice")
            continue
        given[name] = arg
    for name, arg in given.items():
        _indicator_param(n.function, by_name[name], arg, w)
    return Type.NUMBER


def _indicator_param(function: str, param, arg: f.Node, w: _Walk) -> None:
    bounds = f"{param.min:g} to {param.max:g}"
    if isinstance(arg, f.Num):
        if param.integer and not arg.value.is_integer():
            w.refuse(arg, f"`{param.name}` of `{function}` is a whole number")
        elif not param.min <= arg.value <= param.max:
            w.refuse(arg, f"`{param.name}` of `{function}` is {bounds} in the catalogue; this one is {arg.value:g}")
        return
    if isinstance(arg, f.Param):
        decl = _declared(arg, w)
        if decl is None:
            return
        if decl.min < param.min or decl.max > param.max or (param.integer and not decl.integer):
            w.refuse(arg, f"p.{arg.name} may leave the range of `{param.name}` of `{function}` ({bounds})")
        return
    w.refuse(arg, f"`{param.name}` of `{function}` is a number or a parameter, never a formula")


def _squeezed(name: str) -> str:
    return name.upper().replace("_", "")


def _declared(param: f.Param, w: _Walk) -> ParamDecl | None:
    decl = w.scope.params.get(param.name)
    if decl is None:
        w.refuse(param, f"p.{param.name} is not declared in params", hint=_closest(param.name, w.scope.params))
    return decl


def _closest(name: str, candidates) -> str | None:
    found = difflib.get_close_matches(name, list(candidates), n=1, cutoff=0.6)
    return found[0] if found else None


def unreadable_name(name: str) -> bool:
    """A name no formula could refer to as written: Python's parser NFKC-normalises it (`ｃｌｏｓｅ` is `close`) or reads it
    as a keyword."""
    read_as = unicodedata.normalize("NFKC", name)
    return read_as != name or not name.isidentifier() or keyword.iskeyword(name) or keyword.issoftkeyword(name)


def reserved_problem(name: str, path: str, catalogue: Mapping[str, Indicator]) -> Problem | None:
    """A `let` name that would hide a name of the language or of the catalogue, or one no formula could read."""
    if unreadable_name(name) or name in RESERVED or name in catalogue:
        return Problem(path, f"`{name}` cannot name a variable: it is a name of the language or not a name at all")
    return None
