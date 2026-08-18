"""What the module answers with. These models are the published shape.

Separate from the internal ones on purpose. `Candle` carries `forming` and a `source`,
which are how the archive decides what to keep — a consumer has no use for the first on a
settled series and no business acting on the second. What a consumer does need, and what
the internal model leaves implicit, is which side of the spread it is looking at and which
parts of what it asked for were never collected.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .deletion import PairDeletion
from .jobs.models import Chunk, ChunkState, Job, JobPairView, JobStatus
from .jobs.plan import JobEstimate, PairEstimate
from .models import Candle, PriceSide, Resolution
from .rollups import DerivedCandle
from .tracking import CollectionState, TrackedPair


class CandleOut(BaseModel):
    """One settled candle. No `forming`: everything in a range read has closed."""

    time: datetime = Field(description="the start of the candle's period, UTC")
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None

    @classmethod
    def of(cls, candle: Candle | DerivedCandle) -> CandleOut:
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

    # `from` on the wire, `from_` in Python, because the wire name is a keyword here.
    # Written as the two one-way aliases rather than one `alias=`: a type checker builds
    # this model's `__init__` from `alias` alone and then rejects `Uncovered(from_=...)`
    # at every call site. The published document is the same either way — both aliases
    # say `from`, and `populate_by_name` keeps the Python name accepted on input.
    from_: datetime = Field(validation_alias="from", serialization_alias="from")
    to: datetime

    model_config = {"populate_by_name": True}


class FormingState(str, Enum):
    """Why a read of the current period does or does not carry a candle.

    Four answers rather than a candle and a null, because the three empty ones send an
    operator somewhere different: add the pair, come back on Monday, or go and look at why
    collection stopped. Only the last is anybody's problem right now, and without a name it
    reads exactly like the other two.
    """

    FORMING = "forming"
    # Nothing is being collected for this symbol at any resolution.
    NOT_TRACKED = "not_tracked"
    # The venue is shut. There is no current price because there is no trading.
    MARKET_CLOSED = "market_closed"
    # Tracked, and the market is open or the gateway would not say — and still nothing is
    # arriving. This is a collection failure wearing the same empty answer as a quiet
    # weekend, which is the confusion the whole enum exists to prevent.
    NO_QUOTES = "no_quotes"


class FormingCandleOut(BaseModel):
    """The period being built right now, read rather than subscribed to.

    The candle is the same one a subscription's snapshot would carry this instant, and it
    is not stored anywhere: it changes with every quote and understates its own range until
    the period closes. A consumer treating `high`/`low` here as the period's range will be
    wrong before the period ends — which is why `state` says `forming` in words rather than
    leaving it to be inferred from a field being present.
    """

    symbol: str
    resolution: Resolution | None = Field(
        default=None,
        description=(
            "which resolution this candle came from; null when there is none to answer "
            "with. May differ from the one asked for, because a caller that names none is "
            "answered from the finest resolution that actually has quotes arriving"
        ),
    )
    price_side: PriceSide = Field(
        description="which side of the spread this is built from; the archive holds bid"
    )
    state: FormingState
    candle: CandleOut | None = Field(
        default=None, description="null unless `state` is `forming`"
    )
    market_open: bool | None = Field(
        default=None,
        description="null when the gateway could not be asked — not the same as closed",
    )


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
    # Two one-way aliases for one wire name — see `Uncovered.from_`.
    from_: datetime = Field(validation_alias="from", serialization_alias="from")
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
    candle_count: int = Field(description="how many candles are collected for this pair")
    estimated_bytes: int = Field(
        description="a rough estimate of how much storage those candles take, derived "
        "from `candle_count` the same way a job's price is"
    )

    @classmethod
    def of(cls, pair: TrackedPair) -> TrackedPairOut:
        """A pair that has just started being tracked, before anything is collected.

        The three unknowns are said explicitly rather than left to defaults: nothing has
        been collected yet, so there is no earliest and no latest candle, and the state is
        the one that means exactly that. `candle_count` is zero for the same reason, not
        because it is unknown.
        """
        return cls(
            symbol=pair.symbol,
            resolution=pair.resolution,
            added_at=pair.added_at,
            collect_from=pair.collect_from,
            earliest_candle=None,
            latest_candle=None,
            collection=CollectionState.NEVER_COLLECTED,
            candle_count=0,
            estimated_bytes=0,
        )


class PairDeletionOut(BaseModel):
    """What `DELETE /pairs/{symbol}` and `GET /deletions` answer with — the trace of one
    skasowanie, kept after the data itself is gone."""

    symbol: str
    resolution: Resolution
    deleted_at: datetime
    candles_removed: int = Field(description="how many candles were removed; 0 is a valid count")
    removed_from: datetime | None = Field(
        default=None,
        description="the oldest removed candle's period; null together with "
        "`removed_to` when the pair had never collected anything",
    )
    removed_to: datetime | None = Field(
        default=None, description="the newest removed candle's period; null with `removed_from`"
    )

    @classmethod
    def of(cls, deletion: PairDeletion) -> PairDeletionOut:
        return cls(
            symbol=deletion.symbol,
            resolution=deletion.resolution,
            deleted_at=deletion.deleted_at,
            candles_removed=deletion.candles_removed,
            removed_from=deletion.removed_from,
            removed_to=deletion.removed_to,
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
        # `_one_shape_only` has already refused a body with neither, so the single-pair
        # shape always carries a symbol. Stated here because that guarantee lives in a
        # different method and nothing but this line depends on it.
        assert self.symbol is not None
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
    last_activity_at: datetime = Field(
        description=(
            "When something last happened for this pair — a chunk starting counts, not "
            "only one settling, so a long chunk reads as work rather than a stall. Falls "
            "back to the job's creation while no chunk has been claimed yet. This is the "
            "only field that tells a running job apart from a stuck one: progress and "
            "candle counts look identical for both."
        )
    )
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
            last_activity_at=view.last_activity_at,
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
    last_activity_at: datetime = Field(
        description=(
            "When something last happened in this job — a chunk starting counts, not "
            "only one settling. Falls back to the job's creation while no chunk has been "
            "claimed yet."
        )
    )
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
            last_activity_at=job.last_activity_at,
            running_pair=RunningPair(symbol=running[0], resolution=running[1]) if running else None,
            chunks=[ChunkOut.of(chunk) for chunk in job.chunks],
        )


class StreamTicketOut(BaseModel):
    """Permission to open the stream once, and how long it stays good for.

    The lifetime is answered rather than assumed so a consumer can tell a ticket it sat
    on too long from one the archive never issued — the handshake itself cannot say,
    since it refuses both the same way on purpose.
    """

    ticket: str = Field(description="Spend it on the next handshake. It works exactly once.")
    expires_in_seconds: int = Field(
        description="How long from now the ticket stays valid if it goes unused."
    )


class IndicatorParamOut(BaseModel):
    name: str
    type: Literal["int", "float"]
    default: float
    min: float
    max: float


class IndicatorLineSpecOut(BaseModel):
    key: str
    label: str = Field(description="e.g. 'EMA {period}' — a template, not a rendered string")
    style: Literal["line", "dots", "histogram"] | None = Field(
        default=None,
        description=(
            "Overrides the entry's own render.style for this one line — MACD's "
            "histogram line inside an otherwise line-style entry, and the only "
            "reason this field exists. Null means: use render.style."
        ),
    )


class IndicatorRenderOut(BaseModel):
    pane: Literal["price", "own"]
    style: Literal["line", "dots", "histogram"]
    scale: Literal["price", "own", "fixed"] = "price"
    autoscale: bool = Field(
        default=True,
        description="whether this line may widen the price axis it shares — off for an "
        "indicator whose own values are not comparable to price",
    )
    range: tuple[float, float] | None = None
    levels: list[float] = Field(
        default_factory=list, description="reference lines to draw, e.g. 30/70 for RSI"
    )


class IndicatorCatalogueEntryOut(BaseModel):
    """One row of `GET /indicators` — everything a consumer needs to offer this
    indicator and draw it, without knowing anything about it beforehand
    (`market-data-indicators` spec, "Katalog wystarcza do zbudowania wybieraka")."""

    id: str
    name: str
    aliases: list[str] = Field(
        default_factory=list,
        description="names an indicator is also known by; never the vocabulary of one "
        "trading school baked into `id` itself",
    )
    group: str
    output: Literal["lines", "markers", "zones", "levels"]
    params: list[IndicatorParamOut]
    lines: list[IndicatorLineSpecOut] = Field(default_factory=list)
    render: IndicatorRenderOut
    # Exactly the kinds the catalogue can produce, and a test holds the two lists
    # together (`test_indicators_catalogue.py`). A third, "anchored", was declared here
    # and by no entry — a state the wire promised and no producer could reach.
    warmup_kind: Literal["fixed", "decay"]


class IndicatorsCatalogueOut(BaseModel):
    algorithm_version: int
    indicators: list[IndicatorCatalogueEntryOut]


class IndicatorSpecIn(BaseModel):
    id: str = Field(examples=["ema"])
    params: dict[str, float] = Field(default_factory=dict)


class IndicatorsRequest(BaseModel):
    resolution: Resolution = Field(default=Resolution.MINUTE, examples=[Resolution.MINUTE])
    # Two one-way aliases for one wire name — see `Uncovered.from_`.
    from_: datetime = Field(validation_alias="from", serialization_alias="from", description="inclusive, UTC")
    to: datetime = Field(description="exclusive, UTC")
    specs: list[IndicatorSpecIn] = Field(min_length=1)

    model_config = {"populate_by_name": True}


class IndicatorMarkerOut(BaseModel):
    time: datetime
    label: str
    price: float | None = None


class IndicatorZoneOut(BaseModel):
    from_: datetime = Field(validation_alias="from", serialization_alias="from")
    to: datetime | None = Field(
        default=None, description="null while the zone has not closed within the read range"
    )
    top: float
    bottom: float
    direction: Literal["bullish", "bearish"] | None = None
    touched_at: datetime | None = None
    filled_at: datetime | None = None

    model_config = {"populate_by_name": True}


class IndicatorLevelOut(BaseModel):
    from_: datetime = Field(validation_alias="from", serialization_alias="from")
    price: float
    label: str | None = None
    count: int | None = Field(
        default=None,
        description="how many extrema support this level; null for a level that "
        "carries no weight, e.g. a pivot or a previous-period edge",
    )

    model_config = {"populate_by_name": True}


class IndicatorResultOut(BaseModel):
    """One requested indicator's answer. Exactly one of `lines`, `markers`, `zones`,
    `levels` is set — the one its catalogue entry's `output` names — or none of them
    and `error` instead (`market-data-indicators` spec, "Wynik ma jeden z czterech
    kształtów")."""

    id: str
    params: dict[str, float] = Field(description="resolved params — defaults filled in")
    warmup_bars: int | None = Field(
        default=None,
        description="how many bars before the requested range were read for warmup; "
        "null for one that carries an error instead of an answer",
    )
    settled: bool = Field(
        description="false when the archive did not hold enough history before the "
        "requested range for this value to be trusted yet. Says nothing about `error`: "
        "an unsettled value is still a value, computed from a series that was shorter "
        "than it wanted"
    )
    error: str | None = Field(
        default=None,
        description="why this one indicator could not be computed, when the reason is "
        "something the archive does not hold — the series it needs at a resolution "
        "nobody collects. Set instead of a shape, never beside one: an empty `zones` "
        "means the range held none, which is not the same claim. A request the module "
        "refuses outright (unknown indicator, parameter out of range, reversed range, "
        "over the ceiling) is a 422 carrying Problem, not a result carrying this",
    )
    lines: dict[str, list[float | None]] | None = None
    markers: list[IndicatorMarkerOut] | None = None
    zones: list[IndicatorZoneOut] | None = None
    levels: list[IndicatorLevelOut] | None = None

    @model_validator(mode="after")
    def _exactly_one_shape_or_an_error(self) -> IndicatorResultOut:
        """Exactly one shape and no error, or no shape and an error.

        The third combination — a shape *and* a reason — is the one worth refusing to
        build: it reads to a consumer that only looks at the shape as "computed, and it
        was empty", which is the opposite of what happened.
        """
        shapes = (self.lines, self.markers, self.zones, self.levels)
        set_shapes = sum(shape is not None for shape in shapes)
        if self.error is not None:
            if set_shapes != 0:
                raise ValueError("a result carrying an error must carry no shape")
            return self
        if set_shapes != 1:
            raise ValueError(
                "exactly one of lines, markers, zones, levels must be set, or error instead"
            )
        return self


class IndicatorsOut(BaseModel):
    """`POST /indicators/{symbol}` — one or more indicators, on one shared time axis."""

    symbol: str
    resolution: Resolution
    price_side: PriceSide = Field(
        description="which side of the spread these were computed from; the archive holds bid"
    )
    derived: bool = Field(
        description="true when computed from a resolution derived from the minute series"
    )
    algorithm_version: int
    times: list[datetime] = Field(description="shared by every result below")
    warmup_from: datetime | None = Field(
        default=None,
        description="oldest period actually read to satisfy warmup; null when no "
        "requested indicator needed any",
    )
    uncovered: list[Uncovered] = Field(
        default_factory=list,
        description="stretches of the requested range the archive never verified",
    )
    results: list[IndicatorResultOut]


class Problem(BaseModel):
    """A refusal that names itself.

    Never a database error and never a credential — a raw `asyncpg` message tells a
    consumer nothing it can act on while telling anyone reading the logs more about the
    schema than they need, and the caller's own token or stream ticket is never
    something a refusal has any reason to quote back.
    """

    detail: str
