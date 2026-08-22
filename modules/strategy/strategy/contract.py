"""The REST contract: what the operator and the terminal read and write.

Written as models rather than dictionaries so the published document describes it, and so
a field added here has to be added on purpose. Nothing in this file reaches a database or
a strategy — it is the shape of the wire and nothing else.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Problem(BaseModel):
    """A refusal that names itself. Never a database error and never a credential."""

    detail: str


# --- the catalogue --------------------------------------------------------------------


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


# --- parameter sets -------------------------------------------------------------------


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


# --- watches --------------------------------------------------------------------------


class WatchIn(BaseModel):
    strategy_id: str
    symbol: str
    parameter_set_id: int | None = Field(
        default=None,
        description="omit to have a set written from this strategy's defaults",
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


# --- decisions ------------------------------------------------------------------------


class DecisionOut(BaseModel):
    id: int
    strategy_id: str
    symbol: str
    parameter_set_id: int = Field(description="which version of the parameters decided this")
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


class DecisionDetailOut(DecisionOut):
    """One decision with the readings it stood on — enough to re-decide it without the
    archive, which is what makes a recorded decision evidence rather than an anecdote."""

    facts: dict = Field(description="the snapshot `evaluate` was handed")
