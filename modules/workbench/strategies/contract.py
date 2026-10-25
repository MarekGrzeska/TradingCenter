"""The shapes this package answers with. Refusals name themselves and carry every problem, never a database error."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from .costs import CostModel

RunStatus = Literal["queued", "running", "done", "failed", "cancelled"]
Requester = Literal["operator", "agent"]
CostsSource = Literal["request", "broker", "operator", "none"]
_COSTS_SOURCE = (
    "where the run's costs came from: the request, the instrument's profile read off the broker or typed by the "
    "operator, or `none` — a run without costs"
)
_WITHOUT_COSTS = "the result leaves out spread, slippage and financing — a choice, not a model of zeros"


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


class HeadlineOut(BaseModel):
    """The few numbers a list of runs shows; the rest is `GET /runs/{id}`. Null where the report has none."""

    trades: int | None
    total_r: float | None
    expectancy_r: float | None
    max_drawdown_r: float | None
    sharpe: float | None
    costs_source: CostsSource = Field(description=_COSTS_SOURCE)
    without_costs: bool = Field(description=_WITHOUT_COSTS)


class RunSummaryOut(BaseModel):
    id: int
    strategy_id: int
    revision: int
    status: RunStatus
    reason: str | None
    engine_version: int | None
    request: dict
    requested_by: Requester
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    headline: HeadlineOut | None = Field(description="null until the run is done")


class YearOut(BaseModel):
    trades: int
    total_r: float


class CostsByComponentOut(BaseModel):
    spread: float
    slippage: float
    financing: float


class BuyAndHoldOut(BaseModel):
    return_pct: float | None
    entry_price: float | None
    exit_price: float | None


class RandomEntryOut(BaseModel):
    repetitions: int
    seed: int
    entry: Literal["market"]
    average_trades: float | None
    median_total_r: float | None
    p5_total_r: float | None
    p95_total_r: float | None


class SkippedOut(BaseModel):
    skipped: str


class BenchmarksOut(BaseModel):
    buy_and_hold: BuyAndHoldOut | None
    random_entry: RandomEntryOut | SkippedOut | None


class ReportOut(BaseModel):
    """Numbers and nothing else — no field judges the strategy (`strategies-reports`). An unmeasurable number is null,
    never zero."""

    trades: int
    no_trades: bool
    rejected_entries: int
    decision_bars: int
    pessimistic_resolutions: int
    win_rate: float | None
    expectancy_r: float | None
    total_r: float | None
    profit_factor: float | None
    max_drawdown_r: float | None
    longest_losing_streak: int | None
    average_bars_held: float | None
    exposure: float | None
    total_r_without_best_5: float | None
    final_equity: float | None
    return_pct: float | None
    annual_return_pct: float | None
    max_drawdown_pct: float | None
    sharpe: float | None
    sortino: float | None
    calmar: float | None
    by_year: dict[str, YearOut] = Field(description="calendar years (UTC) of the trades' exits")
    costs: CostsByComponentOut
    benchmarks: BenchmarksOut
    annualisation: str
    costs_source: CostsSource = Field(description=_COSTS_SOURCE)
    costs_fetched_at: datetime | None = Field(description="when the broker's profile was read; null for any other source")
    without_costs: bool = Field(description=_WITHOUT_COSTS)
    equity: list[tuple[int, float | None]] | None = Field(
        default=None,
        description="nominal equity at each UTC midnight of the range, epoch seconds — the series the ratios come from; "
        "null for a report of engine version 1, which did not record it",
    )


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
    requested_by: Requester
    report: ReportOut | None
    provenance: dict | None


class StrategyOut(BaseModel):
    id: int
    name: str
    created_at: datetime
    archived_at: datetime | None
    latest_revision: int
    latest_author: Literal["operator", "agent"]
    changed_at: datetime = Field(description="when the latest revision was saved")
    symbol: str
    timeframe: str
    trials: int = Field(description="finished runs of every revision — what was tried, the count overfitting is judged by")
    conversation_id: int | None = Field(
        description="the conversation this strategy is written in — an id in the agent's sessions, never read here"
    )


class SummarySectionOut(BaseModel):
    title: str
    lines: list[str]


class SummaryOut(BaseModel):
    """The document read back in Polish from the document alone, never from a model (`strategies-documents`)."""

    name: str
    sections: list[SummarySectionOut]
    hypothesis: str = Field(description="the author's, verbatim")
    notes: str = Field(description="the author's assumptions, verbatim")


class RevisionOut(BaseModel):
    strategy_id: int
    n: int
    document: dict
    content_hash: str
    schema_version: int
    author: Literal["operator", "agent"]
    created_at: datetime
    summary: SummaryOut | None = Field(description="null only for a document this engine can no longer read")


class RevisionEntryOut(BaseModel):
    n: int
    author: Literal["operator", "agent"]
    created_at: datetime
    content_hash: str


class ChangeOut(BaseModel):
    path: str = Field(description="where in the document, as a problem names it: `entries[0].when`")
    kind: Literal["added", "removed", "changed"]
    before: Any = Field(description="null when added")
    after: Any = Field(description="null when removed")


class ChangesOut(BaseModel):
    strategy_id: int
    n: int
    against: int | None = Field(description="the revision compared with; null when `n` is the first and none was named")
    changes: list[ChangeOut]


class ConflictOut(BaseModel):
    detail: str
    latest_revision: int


class CostProfileOut(BaseModel):
    symbol: str
    costs: CostModel
    updated_at: datetime
    source: Literal["operator", "broker"] = Field(description="who set the values: typed by the operator, or read off the broker")
    fetched_at: datetime | None = Field(description="when the broker was asked; null for the operator's values")
    broker: dict[str, Any] | None = Field(
        description="the broker's own numbers the costs were converted from — bid, ask, overnight rates in its unit and "
        "the moment of its charge; null for the operator's values"
    )


class DraftOut(BaseModel):
    strategy_id: int | None = Field(description="null for the new strategy not saved yet")
    document: dict[str, Any] = Field(description="as the agent put it — not necessarily valid")
    seq: int = Field(description="new with every draft, also one carrying the same document")
    updated_at: datetime


class ConversationIn(BaseModel):
    conversation_id: int | None = Field(ge=1, le=2**63 - 1, description="null forgets the conversation")


class StrategyDetailOut(StrategyOut):
    revision: RevisionOut = Field(description="the latest revision")


class SavedOut(BaseModel):
    strategy_id: int
    revision: int
    created: bool = Field(description="false when the content equalled the latest revision, which is then the answer")


class ValidationOut(BaseModel):
    valid: bool
    problems: list[ProblemOut]
    summary: SummaryOut | None = Field(default=None, description="present when the document is valid")


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
    max_minute_bars: int = Field(description="the most minute candles one run may cover — a run form says it before sending")
