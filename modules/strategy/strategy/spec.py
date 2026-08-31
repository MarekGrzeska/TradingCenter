"""The contract of a catalogue entry: what a strategy declares and what it returns, in four properties that are
enforced — declared facts it does not fetch, a pure `evaluate`, one shape of `Decision`, parameters with ranges."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from .errors import ParamOutOfRange

Direction = Literal["long", "short"]


@dataclass(frozen=True)
class Param:
    """One tunable number, with the range outside which it is not a value at all."""

    name: str
    type: Literal["int", "float"]
    default: float
    min: float
    max: float

    def clamp_or_raise(self, value: float) -> float:
        if not self.min <= value <= self.max:
            raise ParamOutOfRange(self.name, value, self.min, self.max)
        return int(value) if self.type == "int" else float(value)


@dataclass(frozen=True)
class Fact:
    """One thing a strategy needs read on its behalf, named the archive's way. A parameter value may name one of the
    strategy's own, which is what lets a period be tuned; `bars` belongs to the entry, which knows how far back it reads."""

    indicator: str
    resolution: str
    params: Mapping[str, float | str] = field(default_factory=dict)
    # What `Facts[...]` reads it back under. Two facts about the same indicator at different periods are the ordinary
    # case, so the key cannot default to the id alone for more than one of them.
    key: str | None = None
    bars: int = 300

    @property
    def name(self) -> str:
        return self.key or self.indicator

    @property
    def parameter_references(self) -> tuple[str, ...]:
        return tuple(value for value in self.params.values() if isinstance(value, str))

    def resolved_params(self, strategy_params: Mapping[str, float]) -> dict[str, float]:
        """This fact's parameters as numbers, with references substituted."""
        return {
            name: float(strategy_params[value]) if isinstance(value, str) else float(value)
            for name, value in self.params.items()
        }


@dataclass(frozen=True)
class Candle:
    time: datetime
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class Marker:
    time: datetime
    label: str
    price: float | None = None


@dataclass(frozen=True)
class Zone:
    start: datetime
    end: datetime | None
    top: float
    bottom: float
    direction: Direction | None = None
    touched_at: datetime | None = None
    filled_at: datetime | None = None


@dataclass(frozen=True)
class Level:
    time: datetime
    price: float
    label: str | None = None
    count: int | None = None


@dataclass(frozen=True)
class FactValue:
    """One fact as the archive answered it, on its own time axis — not a shared one: a daily structure under
    an hourly decision is the ordinary case, and one axis is where a fact silently becomes a different fact."""

    key: str
    resolution: str
    times: tuple[datetime, ...] = ()
    lines: Mapping[str, tuple[float | None, ...]] = field(default_factory=dict)
    markers: tuple[Marker, ...] = ()
    zones: tuple[Zone, ...] = ()
    levels: tuple[Level, ...] = ()
    # Set when the archive could compute nothing for this one fact — a series it does not hold at that resolution.
    # Never read as "there was nothing": a strategy that cannot see is not a strategy that saw nothing.
    error: str | None = None

    def line(self, name: str) -> tuple[float | None, ...]:
        return self.lines.get(name, ())

    def last(self, name: str) -> float | None:
        """The most recent value of a line, or `None` where the line has not settled."""
        values = self.line(name)
        return values[-1] if values else None

    def previous(self, name: str) -> float | None:
        """The value one bar before the last — the other half of every crossing test."""
        values = self.line(name)
        return values[-2] if len(values) >= 2 else None


@dataclass(frozen=True)
class Facts:
    """Everything `evaluate` is allowed to know. `as_of` is the closing time of the bar being decided on, never the
    wall clock: a decision belongs to a bar, and a replay of that bar has to land on the same answer."""

    symbol: str
    as_of: datetime
    candles: tuple[Candle, ...]
    values: Mapping[str, FactValue] = field(default_factory=dict)

    def __getitem__(self, key: str) -> FactValue:
        return self.values[key]

    def get(self, key: str) -> FactValue | None:
        return self.values.get(key)

    @property
    def close(self) -> float:
        return self.candles[-1].close


@dataclass(frozen=True)
class Decision:
    """What `evaluate` answers, in the one shape everything downstream is written for. A refusal carries its
    reason, a trade its levels and its named features — which is what the backtest attributes an edge to."""

    action: Literal["trade", "no_trade"]
    reason: str | None = None
    direction: Direction | None = None
    entry: float | None = None
    stop: float | None = None
    target: float | None = None
    rr: float | None = None
    score: float | None = None
    features: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.action == "no_trade":
            if not self.reason:
                raise ValueError("a refusal must carry its reason")
            return
        missing = [
            name
            for name, value in (
                ("direction", self.direction),
                ("entry", self.entry),
                ("stop", self.stop),
                ("target", self.target),
            )
            if value is None
        ]
        if missing:
            raise ValueError(f"a trade must carry {', '.join(missing)}")
        if self.entry == self.stop:
            raise ValueError("a trade whose stop is its entry has no risk to size against")

    @classmethod
    def no_trade(cls, reason: str, *, features: Mapping[str, float] | None = None) -> Decision:
        return cls(action="no_trade", reason=reason, features=dict(features or {}))

    @classmethod
    def trade(
        cls,
        *,
        direction: Direction,
        entry: float,
        stop: float,
        target: float,
        score: float | None = None,
        features: Mapping[str, float] | None = None,
        reason: str | None = None,
    ) -> Decision:
        """Reward over risk is computed here rather than passed in — one implementation, at the only place
        that has both numbers. A strategy handing it in could hand in a wrong one."""
        risk = abs(entry - stop)
        reward = abs(target - entry)
        return cls(
            action="trade",
            reason=reason,
            direction=direction,
            entry=entry,
            stop=stop,
            target=target,
            rr=(reward / risk) if risk else None,
            score=score,
            features=dict(features or {}),
        )

    def refused(self, reason: str) -> Decision:
        """This decision as a refusal, keeping what it had worked out: the levels and the score go,
        being no longer claimed, and the features stay, because what the strategy saw is what it saw."""
        return Decision(action="no_trade", reason=reason, features=dict(self.features))


EvaluateFn = Callable[[Facts, Mapping[str, float]], Decision]


@dataclass(frozen=True)
class StrategySpec:
    """One catalogue entry. Adding one changes no file of the runtime."""

    id: str
    name: str
    description: str
    # The bars whose closes drive evaluation, in the archive's vocabulary. A fact may sit on
    # a coarser one; this is the rhythm of the decision itself.
    resolution: str
    evaluate: EvaluateFn
    facts: tuple[Fact, ...] = ()
    params: tuple[Param, ...] = ()
    # How many bars of `resolution` are handed to `evaluate` as `Facts.candles`.
    candles: int = 300

    def __post_init__(self) -> None:
        names = [param.name for param in self.params]
        if len(names) != len(set(names)):
            raise ValueError(f"strategy {self.id!r} declares a parameter twice")
        for param in self.params:
            # A default outside its own range is a strategy that cannot run at all with the
            # settings it ships with — caught at import rather than at the first evaluation.
            param.clamp_or_raise(param.default)
        keys = [fact.name for fact in self.facts]
        if len(keys) != len(set(keys)):
            raise ValueError(
                f"strategy {self.id!r} declares two facts under one key; give one a `key`"
            )
        declared = set(names)
        for fact in self.facts:
            unknown = sorted(set(fact.parameter_references) - declared)
            if unknown:
                # Caught at import, where it is one wrong word, rather than at the first evaluation, where it is a
                # strategy reading a different indicator than the one it was written against.
                raise ValueError(
                    f"strategy {self.id!r} points fact {fact.name!r} at parameter(s) "
                    f"{', '.join(unknown)}, which it does not declare"
                )
        if self.candles < 1:
            raise ValueError(f"strategy {self.id!r} asks for {self.candles} candles")

    def resolve_params(self, requested: Mapping[str, float] | None = None) -> dict[str, float]:
        """Defaults filled in, every value checked against its range. A key the entry does not declare is
        ignored: a set written for a later version should not stop the earlier one from answering."""
        given = dict(requested or {})
        return {
            param.name: param.clamp_or_raise(given.get(param.name, param.default))
            for param in self.params
        }

    @property
    def indicators(self) -> tuple[str, ...]:
        """Every archive indicator this entry depends on, deduplicated."""
        return tuple(dict.fromkeys(fact.indicator for fact in self.facts))


def resolutions_of(spec: StrategySpec) -> Sequence[str]:
    """Every resolution this entry reads, its own included — what the platform must fetch."""
    return tuple(dict.fromkeys((spec.resolution, *(fact.resolution for fact in spec.facts))))
