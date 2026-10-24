"""A formula is read, never run. Python's own parser turns the text into a syntax tree, and only the node types listed
here are carried over into this package's tree — everything else is a refusal naming where it stands. Nothing in this
package hands a formula's text to anything that executes code; the interpreter only ever walks the tree built here.

Python's grammar is borrowed rather than a grammar of our own because every model that will write documents in stage 2
already knows it, and because it already parses what the language needs: `close[1]` is a subscript, `close @ HOUR_4` is
the matrix-multiplication operator, and `7 <= hour < 20` is a chained comparison.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

from .problems import Problem

# Long enough for any condition a person would read, short enough that parsing it is never the cost.
MAX_LENGTH = 2000
# Nesting deeper than this is not a formula anyone means; it is also where Python's parser starts to recurse hard.
MAX_DEPTH = 48


@dataclass(frozen=True)
class Node:
    column: int


@dataclass(frozen=True)
class Num(Node):
    value: float


@dataclass(frozen=True)
class Bool(Node):
    value: bool


@dataclass(frozen=True)
class Name(Node):
    id: str


@dataclass(frozen=True)
class Param(Node):
    """`p.fast` — a value declared in the document's `params`."""

    name: str


@dataclass(frozen=True)
class Neg(Node):
    operand: Node


@dataclass(frozen=True)
class Arith(Node):
    op: str  # one of + - * /
    left: Node
    right: Node


@dataclass(frozen=True)
class Compare(Node):
    """A chain: `a < b <= c` is `ops=("<", "<=")`, `operands=(a, b, c)`."""

    ops: tuple[str, ...]
    operands: tuple[Node, ...]


@dataclass(frozen=True)
class Logic(Node):
    op: str  # "and" | "or"
    values: tuple[Node, ...]


@dataclass(frozen=True)
class Not(Node):
    operand: Node


@dataclass(frozen=True)
class IfElse(Node):
    condition: Node
    then: Node
    otherwise: Node


@dataclass(frozen=True)
class Call(Node):
    function: str
    args: tuple[Node, ...]
    kwargs: tuple[tuple[str, Node], ...]


@dataclass(frozen=True)
class Field(Node):
    """One line of an indicator that draws several: `bbands(20, 2).upper`."""

    value: Node
    name: str


@dataclass(frozen=True)
class Lag(Node):
    """`x[n]` — the value `n` bars back. `n` is a non-negative integer or a parameter, never a formula."""

    value: Node
    bars: int | Param


@dataclass(frozen=True)
class At(Node):
    """`x @ HOUR_4`, `x @ US500`, `x @ "J225"` — the left side read in another resolution or of another instrument.
    Which of the two the name is is decided by the checker, which knows the archive's resolutions."""

    value: Node
    context: str


_ARITH = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/"}
_COMPARE = {ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=", ast.Eq: "==", ast.NotEq: "!="}


class _Refused(Exception):
    def __init__(self, column: int, message: str, hint: str | None = None) -> None:
        self.column = column
        self.message = message
        self.hint = hint


def parse(text: str, path: str) -> tuple[Node | None, list[Problem]]:
    """The formula's tree, or `None` and the reasons it has none. Never raises on what a document can contain."""
    if not isinstance(text, str) or not text.strip():
        return None, [Problem(path, "a formula is expected here, and this one is empty")]
    if len(text) > MAX_LENGTH:
        return None, [Problem(path, f"a formula is at most {MAX_LENGTH} characters; this one is {len(text)}")]
    try:
        tree = ast.parse(text.strip(), mode="eval")
    except SyntaxError as err:
        return None, [Problem(path, f"this is not a formula: {err.msg}", column=err.offset)]
    except (ValueError, RecursionError, MemoryError):
        return None, [Problem(path, "this formula cannot be read: it is nested too deeply or holds a null byte")]
    try:
        return _convert(tree.body, 0), []
    except _Refused as refused:
        return None, [Problem(path, refused.message, column=refused.column, hint=refused.hint)]


def _column(node: ast.AST) -> int:
    return getattr(node, "col_offset", 0) + 1


def _convert(node: ast.AST, depth: int) -> Node:
    if depth > MAX_DEPTH:
        raise _Refused(_column(node), f"this formula nests deeper than {MAX_DEPTH} levels")
    col = _column(node)
    down = depth + 1

    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            return Bool(col, node.value)
        if isinstance(node.value, int | float):
            return Num(col, float(node.value))
        if isinstance(node.value, str):
            raise _Refused(col, "text is allowed only on the right of `@`, as an instrument: close @ \"J225\"")
        raise _Refused(col, f"{type(node.value).__name__} values are not part of the language")
    if isinstance(node, ast.Name):
        return Name(col, node.id)
    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.USub):
            return Neg(col, _convert(node.operand, down))
        if isinstance(node.op, ast.UAdd):
            return _convert(node.operand, down)
        if isinstance(node.op, ast.Not):
            return Not(col, _convert(node.operand, down))
        raise _Refused(col, "this operator is not part of the language")
    if isinstance(node, ast.BinOp):
        if isinstance(node.op, ast.MatMult):
            return At(col, _convert(node.left, down), _context(node.right))
        op = _ARITH.get(type(node.op))
        if op is None:
            raise _Refused(col, "only + - * / are part of the language", hint="powers and modulo are not")
        return Arith(col, op, _convert(node.left, down), _convert(node.right, down))
    if isinstance(node, ast.Compare):
        ops = []
        for op in node.ops:
            symbol = _COMPARE.get(type(op))
            if symbol is None:
                raise _Refused(col, "only < <= > >= == != compare in the language")
            ops.append(symbol)
        operands = (node.left, *node.comparators)
        return Compare(col, tuple(ops), tuple(_convert(o, down) for o in operands))
    if isinstance(node, ast.BoolOp):
        op = "and" if isinstance(node.op, ast.And) else "or"
        return Logic(col, op, tuple(_convert(v, down) for v in node.values))
    if isinstance(node, ast.IfExp):
        return IfElse(col, _convert(node.test, down), _convert(node.body, down), _convert(node.orelse, down))
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise _Refused(col, "only a function of the language can be called, by its name")
        kwargs = []
        for keyword in node.keywords:
            if keyword.arg is None:
                raise _Refused(col, "`**` is not part of the language")
            kwargs.append((keyword.arg, _convert(keyword.value, down)))
        args = []
        for arg in node.args:
            if isinstance(arg, ast.Starred):
                raise _Refused(_column(arg), "`*` unpacking is not part of the language")
            args.append(_convert(arg, down))
        return Call(col, node.func.id, tuple(args), tuple(kwargs))
    if isinstance(node, ast.Attribute):
        if isinstance(node.value, ast.Name) and node.value.id == "p":
            return Param(col, node.attr)
        if isinstance(node.value, ast.Call):
            return Field(col, _convert(node.value, down), node.attr)
        raise _Refused(
            col, "a field is read only from a parameter (p.fast) or from an indicator with several lines",
            hint="bbands(20, 2).upper",
        )
    if isinstance(node, ast.Subscript):
        return Lag(col, _convert(node.value, down), _bars(node.slice))

    raise _Refused(col, f"{_describe(node)} is not part of the language")


def _bars(node: ast.AST) -> int | Param:
    col = _column(node)
    if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
        if node.value < 0:
            raise _Refused(col, "the language does not reach into the future: an offset is 0 or more bars back")
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        raise _Refused(col, "the language does not reach into the future: an offset is 0 or more bars back")
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "p":
        return Param(col, node.attr)
    if isinstance(node, ast.Slice):
        raise _Refused(col, "a range of bars [a:b] is not part of the language; use a window function", hint="highest(high, 20)")
    raise _Refused(col, "an offset is a whole number or a parameter, never a formula")


def _context(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.strip():
        return node.value.strip()
    raise _Refused(
        _column(node), "the right of `@` is a resolution or an instrument, named, never a formula",
        hint="close @ HOUR_4, close @ US500",
    )


_DESCRIPTIONS: dict[type, str] = {
    ast.Lambda: "a lambda",
    ast.ListComp: "a list comprehension",
    ast.SetComp: "a set comprehension",
    ast.DictComp: "a dict comprehension",
    ast.GeneratorExp: "a generator expression",
    ast.NamedExpr: "an assignment",
    ast.List: "a list",
    ast.Tuple: "a tuple",
    ast.Dict: "a dict",
    ast.Set: "a set",
    ast.JoinedStr: "an f-string",
    ast.Await: "await",
    ast.Yield: "yield",
}


def _describe(node: ast.AST) -> str:
    return _DESCRIPTIONS.get(type(node), type(node).__name__)
