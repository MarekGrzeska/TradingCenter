"""The REST contract: what the operator and the terminal read and write. Nothing here reaches a database
or a strategy — it is the shape of the wire and nothing else.

The rule travels as itself: `RuleDefinition` comes from `rule.py` rather than being restated, so the wire,
the stored row and the interpreter can never disagree about what a node is."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from .rule import RuleDefinition


class Problem(BaseModel):
    """A refusal that names itself. Never a database error and never a credential."""

    detail: str



class ParamOut(BaseModel):
    name: str
    type: Literal["int", "float"]
    default: float
    min: float
    max: float


class FactOut(BaseModel):
    key: str = Field(description="what the strategy reads this back under")
    indicator: str = Field(description="the archive's catalogue id")
    resolution: str
    params: dict[str, float | str] = Field(
        description="a string names one of this strategy's own parameters"
    )
    bars: int


class StrategyOut(BaseModel):
    """One catalogue entry as it can be read from outside — everything but its function."""

    id: str
    name: str
    description: str
    resolution: str = Field(description="the bars whose closes drive evaluation")
    candles: int
    facts: list[FactOut]
    params: list[ParamOut]
    source: Literal["code", "revision"] = Field(
        default="code",
        description="whether this entry is code in the deployed image or a stored "
        "revision — a coded entry has no revisions and cannot be edited",
    )
    revision: int | None = Field(
        default=None, description="the revision this was built from; null for a coded entry"
    )



class DefinitionIn(BaseModel):
    """A new clicked strategy: its identity, its name, and the first version of its rule."""

    strategy_id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_]*$",
        description="lowercase, from the same namespace the coded entries use — one that "
        "a coded entry already claims is refused",
    )
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2_000)
    definition: RuleDefinition


class RevisionIn(BaseModel):
    """The next revision of an existing definition. The previous one stays as it was."""

    definition: RuleDefinition


class DefinitionPatch(BaseModel):
    """The two things about a definition that are not the rule. Changed in place rather than minted as a
    revision: provenance that shifted because somebody fixed a typo is provenance nobody could trust."""

    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2_000)


class DefinitionOut(BaseModel):
    id: int
    strategy_id: str
    name: str
    description: str
    latest_version: int = Field(
        description="the newest revision; a running watch may still be pinned to an older one"
    )
    created_at: datetime


class RevisionOut(BaseModel):
    id: int
    strategy_id: str
    version: int
    definition: RuleDefinition
    created_at: datetime



class ParameterSetIn(BaseModel):
    strategy_id: str
    params: dict[str, float] = Field(
        default_factory=dict, description="defaults are filled in for anything omitted"
    )


class ParameterSetOut(BaseModel):
    id: int
    strategy_id: str
    version: int = Field(description="append-only; a change of mind is the next version")
    params: dict[str, float] = Field(description="resolved — defaults filled in")
    created_at: datetime
    strategy_revision_id: int | None = Field(
        default=None,
        description="the revision whose declaration these values were checked against; "
        "null for a coded entry, whose declaration is in the image",
    )



class WatchIn(BaseModel):
    strategy_id: str
    symbol: str
    parameter_set_id: int | None = Field(
        default=None,
        description="omit to have a set written from this strategy's defaults",
    )
    revision: int | None = Field(
        default=None,
        description="which revision to pin this watch to; omit for the newest at this "
        "moment. A watch never follows later revisions — moving it is a second call",
    )


class WatchPatch(BaseModel):
    active: bool


class WatchOut(BaseModel):
    id: int
    strategy_id: str
    symbol: str
    parameter_set_id: int
    active: bool
    created_at: datetime
    strategy_revision_id: int | None = Field(
        default=None,
        description="the revision this watch computes — pinned, never followed. Null means "
        "the strategy is code in the image",
    )



class DecisionOut(BaseModel):
    id: int
    strategy_id: str
    symbol: str
    parameter_set_id: int = Field(description="which version of the parameters decided this")
    strategy_revision_id: int | None = Field(
        default=None, description="which revision of the rule decided this; null for code"
    )
    strategy_revision: int | None = Field(
        default=None, description="that revision's own number, so a reader needs no second call"
    )
    as_of: datetime = Field(description="the closing time of the bar decided on, never a wall clock")
    action: Literal["trade", "no_trade"]
    reason: str | None = None
    reason_kind: Literal["strategy", "coverage", "limit"] | None = Field(
        default=None,
        description="which layer refused: the strategy itself, a gap in the data, or a "
        "platform limit. A gap is answered by fetching history; the strategy's own no is "
        "answered by reading the strategy",
    )
    direction: Literal["long", "short"] | None = None
    entry: float | None = None
    stop: float | None = None
    target: float | None = None
    rr: float | None = Field(default=None, description="reward over risk, from the levels")
    score: float | None = None
    features: dict[str, float] = Field(
        default_factory=dict, description="what the strategy measured, named"
    )
    created_at: datetime


class BacktestRunOut(BaseModel):
    """One kept report. The three fields before `report` are the ones two runs must share before their
    numbers may be read together — as fields, so a caller can check that without parsing the blob."""

    id: int
    strategy_id: str
    strategy_revision_id: int | None = Field(
        default=None, description="the revision this run computed; null for a coded entry"
    )
    symbol: str
    resolution: str
    range_from: datetime
    range_to: datetime
    params: dict[str, float]
    costs: dict[str, float]
    report: dict
    ran_at: datetime


class DecisionDetailOut(DecisionOut):
    """One decision with the readings it stood on — enough to re-decide it without the
    archive, which is what makes a recorded decision evidence rather than an anecdote."""

    facts: dict = Field(description="the snapshot `evaluate` was handed")
