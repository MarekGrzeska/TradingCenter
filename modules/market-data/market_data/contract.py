"""What the module answers with. These models are the published shape.

Separate from the internal ones on purpose. `Candle` carries `forming` and a `source`,
which are how the archive decides what to keep — a consumer has no use for the first on a
settled series and no business acting on the second. What a consumer does need, and what
the internal model leaves implicit, is which side of the spread it is looking at and which
parts of what it asked for were never collected.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

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


class TrackedPairOut(BaseModel):
    symbol: str
    resolution: Resolution
    added_at: datetime
    latest_candle: datetime | None = Field(
        default=None, description="the newest period collected, or null if none yet"
    )
    collection: CollectionState = Field(
        description="whether data is actually arriving, as far as the archive can tell"
    )


class TrackPairRequest(BaseModel):
    symbol: str = Field(examples=["US100"])
    resolution: Resolution = Field(default=Resolution.MINUTE, examples=[Resolution.MINUTE])


class Problem(BaseModel):
    """A refusal that names itself.

    Never a database error and never a credential — there is no credential on this path to
    leak, and a raw `asyncpg` message tells a consumer nothing it can act on while telling
    anyone reading the logs more about the schema than they need.
    """

    detail: str
