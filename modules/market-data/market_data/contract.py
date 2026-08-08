"""What the module answers with. These models are the published shape.

Separate from the internal ones on purpose. `Candle` carries `forming` and a `source`,
which are how the archive decides what to keep — a consumer has no use for the first on a
settled series and no business acting on the second. What a consumer does need, and what
the internal model leaves implicit, is which side of the spread it is looking at and which
parts of what it asked for were never collected.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from .jobs.models import Chunk, ChunkState, Job, JobPairView, JobStatus
from .jobs.plan import JobEstimate, PairEstimate
from .models import Candle, PriceSide, Resolution
from .tracking import CollectionState


class CandleOut(BaseModel):
    """One settled candle. No `forming`: everything in a range read has closed."""

    time: datetime = Field(description="the start of the candle's period, UTC")
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None

    @classmethod
    def of(cls, candle: Candle) -> CandleOut:
        return cls(
            time=candle.period_start,
            open=candle.open,
            high=candle.high,
            low=candle.low,
            close=candle.close,
            volume=candle.volume,
        )


class Uncovered(BaseModel):
    """A stretch of the requested range the archive has never looked at."""

    from_: datetime = Field(alias="from")
    to: datetime

    model_config = {"populate_by_name": True}


class CandlesOut(BaseModel):
    """A range read, and everything needed to know what it is not saying.

    `uncovered` is the part that matters and the part a plain list of candles cannot
    express. An empty series over a weekend and an empty series because ingest was down
    are the same list; only one of them is the whole story.
    """

    symbol: str
    resolution: Resolution
    price_side: PriceSide = Field(
        description="which side of the spread these are built from; the archive holds bid"
    )
    derived: bool = Field(
        description=(
            "true when the series was computed from the minute series rather than "
            "collected at this resolution"
        )
    )
    candles: list[CandleOut]
    uncovered: list[Uncovered] = Field(
        default_factory=list,
        description="stretches of the requested range the archive never verified",
    )


class CoverageOut(BaseModel):
    from_: datetime = Field(alias="from")
    to: datetime
    history_ended: bool = Field(
        description="true when the provider has nothing older than `from`"
    )

    model_config = {"populate_by_name": True}


class PairCoverageOut(BaseModel):
    symbol: str
    resolution: Resolution
    ranges: list[CoverageOut]
    earliest_reachable: datetime | None = Field(
        default=None,
        description=(
            "the oldest moment worth asking the provider about; null means the end of "
            "its history has not been reached, not that there is no limit"
        ),
    )


class FillOut(BaseModel):
    """What this pair's most recent backfill did, and what it cost.

    A fill can run for tens of minutes and fail on one pair while the others carry on, so
    where it got to is part of what is being asked when somebody asks what is collected —
    not something to go and read a log for. `summary` is the same one line the module
    logs, so an operator comparing the two is comparing one sentence with itself.
    """

    finished_at: datetime | None = Field(
        default=None, description="when this fill ended; null while it is still running"
    )
    requested: int = Field(description="candles asked of the gateway; 0 means nothing was asked")
    written: int = Field(
        default=0,
        description="rows the archive took, which is not always how many arrived — a "
        "streamed value never displaces a stored history one",
    )
    requests: int = Field(
        default=0, description="provider calls the gateway made behind that one request"
    )
    failure: str | None = Field(
        default=None, description="why it failed, named; null when it did not"
    )
    summary: str = Field(description="the whole outcome as one line, for a person")


class TrackedPairOut(BaseModel):
    symbol: str
    resolution: Resolution
    added_at: datetime
    collect_from: datetime = Field(
        description="the moment history for this pair is meant to reach back to"
    )
    earliest_candle: datetime | None = Field(
        default=None,
        description="the oldest period collected — how far back the data actually reaches, "
        "which is not `collect_from` (where it was asked to reach) — or null if none yet",
    )
    latest_candle: datetime | None = Field(
        default=None, description="the newest period collected, or null if none yet"
    )
    collection: CollectionState = Field(
        description="whether data is actually arriving, as far as the archive can tell"
    )
    last_fill: FillOut | None = Field(
        default=None,
        description="the pair's most recent backfill, or null if none has run since the "
        "module started — fills live in memory and do not survive a restart",
    )


class PairRequest(BaseModel):
    symbol: str = Field(examples=["US100"])
    resolution: Resolution = Field(default=Resolution.MINUTE, examples=[Resolution.MINUTE])


class TrackPairRequest(BaseModel):
    """Body for `POST /pairs`.

    Two shapes, never mixed: the original single-pair one (`symbol`, `resolution`,
    still meaning exactly what it always did — no `collect_from` is the default depth)
    and a multi-pair one (`pairs`, `collect_from`) for adding several pairs as one
    decision. A consumer that has never heard of `pairs` keeps working unchanged.
    """

    symbol: str | None = Field(default=None, examples=["US100"])
    resolution: Resolution = Field(default=Resolution.MINUTE, examples=[Resolution.MINUTE])
    pairs: list[PairRequest] | None = Field(
        default=None, description="multiple pairs added as one decision; excludes `symbol`"
    )
    collect_from: datetime | None = Field(
        default=None,
        description="moment history should reach back to; omitted means the configured "
        "default depth, exactly as before this field existed",
    )

    @model_validator(mode="after")
    def _one_shape_only(self) -> TrackPairRequest:
        if self.symbol is not None and self.pairs is not None:
            raise ValueError("give either `symbol` or `pairs`, not both")
        if self.symbol is None and not self.pairs:
            raise ValueError("give either `symbol` or a non-empty `pairs`")
        return self

    def resolved_pairs(self) -> list[PairRequest]:
        if self.pairs is not None:
            return self.pairs
        return [PairRequest(symbol=self.symbol, resolution=self.resolution)]


class TrackedPairResult(BaseModel):
    """One pair's outcome from `POST /pairs` — never a bare list of pairs, because a
    refusal for one must not be indistinguishable from silence about it."""

    symbol: str
    resolution: Resolution
    pair: TrackedPairOut | None = Field(
        default=None, description="present when this pair was accepted"
    )
    refused: str | None = Field(
        default=None, description="why this pair was refused; null when it was accepted"
    )


class TrackPairsResult(BaseModel):
    results: list[TrackedPairResult]
    job_id: int | None = Field(
        default=None,
        description="the backfill job covering the accepted pairs, or null when nothing "
        "needed fetching",
    )


class EstimateRequest(BaseModel):
    pairs: list[PairRequest]
    collect_from: datetime = Field(description="moment history should reach back to")


class PairEstimateOut(BaseModel):
    symbol: str
    resolution: Resolution
    effective_from: datetime | None = Field(
        default=None,
        description="what `collect_from` was actually clipped to; null when the symbol "
        "is unknown to the gateway",
    )
    clipped: bool = Field(
        default=False, description="true when `effective_from` differs from `collect_from`"
    )
    estimated_candles: int = 0
    estimated_bytes: int = 0
    unknown: bool = Field(
        default=False, description="true when the gateway does not know this symbol"
    )

    @classmethod
    def of(cls, estimate: PairEstimate) -> PairEstimateOut:
        return cls(
            symbol=estimate.symbol,
            resolution=estimate.resolution,
            effective_from=estimate.effective_from,
            clipped=estimate.clipped,
            estimated_candles=estimate.estimated_candles,
            estimated_bytes=estimate.estimated_bytes,
        )

    @classmethod
    def unknown_pair(cls, symbol: str, resolution: Resolution) -> PairEstimateOut:
        return cls(symbol=symbol, resolution=resolution, unknown=True)


class JobEstimateOut(BaseModel):
    pairs: list[PairEstimateOut]
    total_estimated_candles: int
    total_estimated_bytes: int

    @classmethod
    def of(cls, estimate: JobEstimate) -> JobEstimateOut:
        return cls(
            pairs=[PairEstimateOut.of(p) for p in estimate.pairs],
            total_estimated_candles=estimate.total_estimated_candles,
            total_estimated_bytes=estimate.total_estimated_bytes,
        )


class ChunkOut(BaseModel):
    id: int
    symbol: str
    resolution: Resolution
    chunk_start: datetime
    chunk_end: datetime
    state: ChunkState
    attempt: int
    candles_written: int
    requests: int
    failure: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @classmethod
    def of(cls, chunk: Chunk) -> ChunkOut:
        return cls(
            id=chunk.id,
            symbol=chunk.symbol,
            resolution=chunk.resolution,
            chunk_start=chunk.chunk_start,
            chunk_end=chunk.chunk_end,
            state=chunk.state,
            attempt=chunk.attempt,
            candles_written=chunk.candles_written,
            requests=chunk.requests,
            failure=chunk.failure,
            started_at=chunk.started_at,
            finished_at=chunk.finished_at,
        )


class RunningPair(BaseModel):
    symbol: str
    resolution: Resolution


class JobPairViewOut(BaseModel):
    """One job, narrowed to one pair — what `GET /jobs` answers with."""

    job_id: int
    symbol: str
    resolution: Resolution
    created_at: datetime
    requested_from: datetime
    attempt: int
    status: JobStatus
    chunks_done: int
    chunks_total: int
    candles_written: int
    chunks: list[ChunkOut]

    @classmethod
    def of(cls, view: JobPairView) -> JobPairViewOut:
        done, total = view.progress
        return cls(
            job_id=view.job_id,
            symbol=view.symbol,
            resolution=view.resolution,
            created_at=view.created_at,
            requested_from=view.requested_from,
            attempt=view.attempt,
            status=view.status,
            chunks_done=done,
            chunks_total=total,
            candles_written=view.candles_written,
            chunks=[ChunkOut.of(chunk) for chunk in view.chunks],
        )


class JobOut(BaseModel):
    """A whole job — every pair it touched. What `GET /jobs/{id}` and
    `POST /jobs/{id}/retry` answer with; `GET /jobs` answers with `JobPairViewOut`."""

    id: int
    created_at: datetime
    requested_from: datetime
    attempt: int
    status: JobStatus
    chunks_done: int
    chunks_total: int
    candles_written: int
    running_pair: RunningPair | None = None
    chunks: list[ChunkOut]

    @classmethod
    def of(cls, job: Job) -> JobOut:
        done, total = job.progress
        running = job.running_pair
        return cls(
            id=job.id,
            created_at=job.created_at,
            requested_from=job.requested_from,
            attempt=job.attempt,
            status=job.status,
            chunks_done=done,
            chunks_total=total,
            candles_written=job.candles_written,
            running_pair=RunningPair(symbol=running[0], resolution=running[1]) if running else None,
            chunks=[ChunkOut.of(chunk) for chunk in job.chunks],
        )


class Problem(BaseModel):
    """A refusal that names itself.

    Never a database error and never a credential — there is no credential on this path to
    leak, and a raw `asyncpg` message tells a consumer nothing it can act on while telling
    anyone reading the logs more about the schema than they need.
    """

    detail: str
