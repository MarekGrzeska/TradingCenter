"""A rule as data: the closed vocabulary a clicked-together strategy is built from, a tree of typed nodes and never a
text, which is what makes it safe to run a rule nobody reviewed. What needs the archive lives in `rule_validation.py`."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .periods import RESOLUTIONS

# The ceilings. Each is far above anything the two real strategies need and far below what would make one
# evaluation expensive: a rule is walked once per bar per watch.
MAX_FACTS = 12
MAX_PARAMS = 24
MAX_NODES = 400
MAX_DEPTH = 24
MAX_GUARDS = 12
MAX_SETUPS = 4
MAX_FEATURES = 16
# How far back a single read may reach. One bar back is what a crossing needs; the rest is
# room for a rule comparing against a recent extreme without turning into a loop.
MAX_OFFSET = 50


class _Node(BaseModel):
    """Every node is closed to unknown keys. `extra="forbid"` is doing real work: a misspelled key in an
    otherwise valid tree would be dropped in silence, and the rule would answer a slightly different question."""

    model_config = ConfigDict(extra="forbid")



class Const(_Node):
    node: Literal["const"] = "const"
    value: float


class ParamRef(_Node):
    node: Literal["param"] = "param"
    name: str = Field(min_length=1)


class FactRead(_Node):
    """One line of one declared fact, at this bar or a few bars back. `offset` counts backwards from the bar being
    decided on, so `0` is the reading the loop calls "now" and `1` is the other half of every crossing test."""

    node: Literal["fact"] = "fact"
    key: str = Field(min_length=1)
    line: str = Field(min_length=1)
    offset: int = Field(default=0, ge=0, le=MAX_OFFSET)


class BarRead(_Node):
    node: Literal["bar"] = "bar"
    field: Literal["open", "high", "low", "close"] = "close"
    offset: int = Field(default=0, ge=0, le=MAX_OFFSET)


class Arith(_Node):
    node: Literal["arith"] = "arith"
    op: Literal["+", "-", "*", "/"]
    operands: list[Numeric] = Field(min_length=2)

    @model_validator(mode="after")
    def _arity(self) -> Arith:
        # Subtraction and division are written binary and folded nowhere: `a - b - c` reads two ways to a
        # human and one way to a machine, and offering the ambiguous spelling invites the misreading.
        if self.op in {"-", "/"} and len(self.operands) != 2:
            raise ValueError(f"{self.op!r} takes exactly two operands")
        return self


class Call(_Node):
    node: Literal["call"] = "call"
    fn: Literal["abs", "min", "max", "round"]
    operands: list[Numeric] = Field(min_length=1)

    @model_validator(mode="after")
    def _arity(self) -> Call:
        expected = {"abs": (1, 1), "min": (2, None), "max": (2, None), "round": (2, 2)}
        low, high = expected[self.fn]
        if len(self.operands) < low or (high is not None and len(self.operands) > high):
            wanted = f"{low}" if high == low else f"at least {low}"
            raise ValueError(f"{self.fn!r} takes {wanted} operand(s)")
        if self.fn == "round" and not isinstance(self.operands[1], Const):
            # Rounding to a number that varies with the readings is a rule whose precision
            # depends on the market, which is never what anybody means.
            raise ValueError("round's second operand must be a constant number of digits")
        return self


class Previous(_Node):
    """The same expression, evaluated one bar earlier — a frame shift rather than an offset on every leaf inside it:
    `previous(fast − slow)` says what it means, while shifting each leaf by hand is three places to forget one."""

    node: Literal["previous"] = "previous"
    of: Numeric


Numeric = Annotated[
    Const | ParamRef | FactRead | BarRead | Arith | Call | Previous,
    Field(discriminator="node"),
]



class Compare(_Node):
    node: Literal["compare"] = "compare"
    op: Literal["<", "<=", ">", ">="]
    left: Numeric
    right: Numeric


class Logic(_Node):
    node: Literal["logic"] = "logic"
    op: Literal["all", "any", "not"]
    operands: list[Condition] = Field(min_length=1)

    @model_validator(mode="after")
    def _arity(self) -> Logic:
        if self.op == "not" and len(self.operands) != 1:
            raise ValueError("'not' takes exactly one operand")
        return self


class Crossed(_Node):
    """Two expressions crossing on this bar — the one piece of sugar in the vocabulary. A crossing expressed
    as four comparisons over two frames is four places for one of them to drift."""

    node: Literal["crossed"] = "crossed"
    direction: Literal["above", "below"]
    left: Numeric
    right: Numeric


class Settled(_Node):
    """Whether every one of these readings exists at all. Never undetermined itself: it is how a rule asks
    about that state instead of being carried along by it, ahead of the guards."""

    node: Literal["settled"] = "settled"
    of: list[Numeric] = Field(min_length=1)


Condition = Annotated[
    Compare | Logic | Crossed | Settled,
    Field(discriminator="node"),
]



class RuleParam(BaseModel):
    """One tunable number of a clicked strategy, with the range outside which it is not a
    value at all. The same shape `spec.Param` has, on the wire and in the row."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    type: Literal["int", "float"]
    default: float
    min: float
    max: float

    @model_validator(mode="after")
    def _range_holds_its_default(self) -> RuleParam:
        if self.min > self.max:
            raise ValueError(f"parameter {self.name!r} has min above max")
        if not self.min <= self.default <= self.max:
            raise ValueError(
                f"parameter {self.name!r} defaults to {self.default}, outside "
                f"[{self.min}, {self.max}] — it could not run with what it ships with"
            )
        return self


class RuleFact(BaseModel):
    """One reading the platform fetches on this rule's behalf, named the archive's way."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, description="what the rule reads this back under")
    indicator: str = Field(min_length=1, description="the archive's catalogue id")
    resolution: str
    params: dict[str, float | str] = Field(
        default_factory=dict,
        description="a string names one of this rule's own parameters",
    )
    bars: int = Field(default=300, ge=1, le=200_000)

    @model_validator(mode="after")
    def _resolution_is_one_the_archive_has(self) -> RuleFact:
        if self.resolution not in RESOLUTIONS:
            raise ValueError(
                f"fact {self.key!r} names resolution {self.resolution!r}; the archive's are "
                f"{', '.join(RESOLUTIONS)}"
            )
        return self


class Guard(BaseModel):
    """A reason to refuse, in the order it should be asked: the cheapest and commonest refusal belongs first, since
    the usual answer of a strategy worth running is "no"."""

    model_config = ConfigDict(extra="forbid")

    when: Condition
    reason: str = Field(min_length=1)


class Setup(BaseModel):
    """One way this rule says yes — a direction, its levels, and what it calls itself."""

    model_config = ConfigDict(extra="forbid")

    when: Condition
    direction: Literal["long", "short"]
    entry: Numeric
    stop: Numeric
    target: Numeric
    score: Numeric | None = None
    reason: str = Field(min_length=1)


class RuleDefinition(BaseModel):
    """The whole of what a revision carries. `unsettled_reason` is declared rather than fixed by the
    platform: "it has not settled" means something different for an average than for a structure."""

    model_config = ConfigDict(extra="forbid")

    resolution: str = Field(description="the bars whose closes drive evaluation")
    candles: int = Field(default=300, ge=1, le=200_000)
    unsettled_reason: str = Field(min_length=1)
    no_setup_reason: str = Field(min_length=1)
    facts: list[RuleFact] = Field(default_factory=list, max_length=MAX_FACTS)
    params: list[RuleParam] = Field(default_factory=list, max_length=MAX_PARAMS)
    guards: list[Guard] = Field(default_factory=list, max_length=MAX_GUARDS)
    setups: list[Setup] = Field(min_length=1, max_length=MAX_SETUPS)
    features: dict[str, Numeric] = Field(default_factory=dict, max_length=MAX_FEATURES)

    @model_validator(mode="after")
    def _coheres(self) -> RuleDefinition:
        if self.resolution not in RESOLUTIONS:
            raise ValueError(
                f"the rule decides on {self.resolution!r}; the archive's resolutions are "
                f"{', '.join(RESOLUTIONS)}"
            )
        _refuse_duplicates([param.name for param in self.params], "parameter")
        _refuse_duplicates([fact.key for fact in self.facts], "fact key")

        declared_params = {param.name for param in self.params}
        declared_facts = {fact.key for fact in self.facts}
        for fact in self.facts:
            unknown = sorted(
                value
                for value in fact.params.values()
                if isinstance(value, str) and value not in declared_params
            )
            if unknown:
                raise ValueError(
                    f"fact {fact.key!r} points at parameter(s) {', '.join(unknown)}, "
                    "which this rule does not declare"
                )
        for node in self.walk():
            if isinstance(node, ParamRef) and node.name not in declared_params:
                raise ValueError(f"the rule reads parameter {node.name!r}, which it does not declare")
            if isinstance(node, FactRead) and node.key not in declared_facts:
                raise ValueError(f"the rule reads fact {node.key!r}, which it does not declare")

        nodes = sum(1 for _ in self.walk())
        if nodes > MAX_NODES:
            raise ValueError(f"the rule has {nodes} nodes; the ceiling is {MAX_NODES}")
        depth = self.depth()
        if depth > MAX_DEPTH:
            raise ValueError(f"the rule nests {depth} deep; the ceiling is {MAX_DEPTH}")
        return self

    def roots(self) -> list[BaseModel]:
        """Every expression this definition holds, in no particular order."""
        found: list[BaseModel] = [guard.when for guard in self.guards]
        for setup in self.setups:
            found += [setup.when, setup.entry, setup.stop, setup.target]
            if setup.score is not None:
                found.append(setup.score)
        found += list(self.features.values())
        return found

    def walk(self) -> Iterator[BaseModel]:
        for root in self.roots():
            yield from walk(root)

    def depth(self) -> int:
        return max((depth(root) for root in self.roots()), default=0)


def walk(node: BaseModel) -> Iterator[BaseModel]:
    """Every node of one expression, itself included."""
    yield node
    for child in _children(node):
        yield from walk(child)


def depth(node: BaseModel) -> int:
    return 1 + max((depth(child) for child in _children(node)), default=0)


def _children(node: BaseModel) -> list[BaseModel]:
    if isinstance(node, Arith | Call):
        return list(node.operands)
    if isinstance(node, Logic):
        return list(node.operands)
    if isinstance(node, Previous):
        return [node.of]
    if isinstance(node, Compare | Crossed):
        return [node.left, node.right]
    if isinstance(node, Settled):
        return list(node.of)
    return []


def _refuse_duplicates(names: list[str], what: str) -> None:
    seen: set[str] = set()
    for name in names:
        if name in seen:
            raise ValueError(f"the rule declares {what} {name!r} twice")
        seen.add(name)


# Every model above names its children by a type alias defined after it, so the references stay strings
# until here. Without this the discriminated unions are never built and the first parse fails.
for _model in (Arith, Call, Previous, Compare, Logic, Crossed, Settled, Setup, RuleDefinition):
    _model.model_rebuild()
