"""The shapes this package answers with. Refusals name themselves and carry every problem, never a database error."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

RunStatus = Literal["queued", "running", "done", "failed", "cancelled"]


class ProblemOut(BaseModel):
    path: str = Field(description="where in the document or request, e.g. `entries[0].when`")
    message: str
    column: int | None = Field(description="1-based character in the formula, when the problem is in one")
    hint: str | None = Field(description="the nearest known name, or what to write instead")


class ProblemsOut(BaseModel):
    detail: str
    problems: list[ProblemOut]


class RunAcceptedOut(BaseModel):
    id: int
    strategy_id: int
    revision: int = Field(description="the revision the run is of — the latest at the moment it was asked, if none was named")
    status: RunStatus


class RunCancelledOut(BaseModel):
    id: int
    status: RunStatus = Field(description="the status after the request")
    was: RunStatus = Field(description="the status the run had when the cancellation arrived")


class RunSummaryOut(BaseModel):
    id: int
    strategy_id: int
    revision: int
    status: RunStatus
    reason: str | None
    engine_version: int | None
    request: dict
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class RunOut(BaseModel):
    id: int
    strategy_id: int
    revision: int
    status: RunStatus
    reason: str | None
    engine_version: int | None
    request: dict
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    report: dict | None
    provenance: dict | None


class StrategyOut(BaseModel):
    id: int
    name: str
    created_at: datetime
    archived_at: datetime | None
    latest_revision: int
    trials: int = Field(description="finished runs of every revision — what was tried, the count overfitting is judged by")


class RevisionOut(BaseModel):
    strategy_id: int
    n: int
    document: dict
    content_hash: str
    schema_version: int
    author: Literal["operator", "agent"]
    created_at: datetime


class StrategyDetailOut(StrategyOut):
    revision: RevisionOut = Field(description="the latest revision")


class SavedOut(BaseModel):
    strategy_id: int
    revision: int
    created: bool = Field(description="false when the content equalled the latest revision, which is then the answer")


class ValidationOut(BaseModel):
    valid: bool
    problems: list[ProblemOut]


class FunctionOut(BaseModel):
    name: str
    signature: str
    description: str
    places: list[str] | None = Field(description="where in a document it may stand; null is everywhere")


class IndicatorOut(BaseModel):
    id: str
    signature: str
    lines: list[str]


class LanguageOut(BaseModel):
    schema_version: int
    sections: list[str]
    constructions: list[str]
    series: dict[str, str]
    time: dict[str, str]
    constants: dict[str, float]
    position: dict[str, str] = Field(description="the open position — in exits only")
    history: dict[str, str] = Field(description="closed trades — anywhere but a `let`")
    resolutions: list[str]
    functions: list[FunctionOut]
    indicators: list[IndicatorOut] | None = Field(
        description="the archive's line indicators as functions; null when the archive did not answer"
    )
    max_bars: int


class TradeOut(BaseModel):
    seq: int
    side: Literal["long", "short"]
    entry_time: datetime
    entry_price: float
    exit_time: datetime
    exit_price: float
    units: float
    initial_stop: float
    result_r: float
    result_money: float
    costs: dict
    exit_reason: Literal["stop", "target", "trail", "when", "max_bars", "end_of_range"]
    pessimistic: bool


class TradesPageOut(BaseModel):
    run_id: int
    total: int
    trades: list[TradeOut]


class QueueOut(BaseModel):
    queued: int
    running: int


class HealthOut(BaseModel):
    database: Literal["reachable"]
    queue: QueueOut
