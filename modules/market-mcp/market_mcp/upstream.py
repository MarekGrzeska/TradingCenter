"""Narrow pydantic models for the shapes this module reads off market-data's wire.

Deliberately narrow: each model carries only the fields a tool actually uses, not the
whole contract — this module does not import `market_data.contract`
(specs/market-mcp-upstream-access, "Kontrakt archiwum jest sprawdzany, nie zakładany").
A field a tool starts reading gets added here, and nowhere else.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class UpstreamCandle(BaseModel):
    time: datetime
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None


class UpstreamUncovered(BaseModel):
    from_: datetime = Field(alias="from")
    to: datetime


class UpstreamCandles(BaseModel):
    symbol: str
    resolution: str
    derived: bool
    candles: list[UpstreamCandle]
    uncovered: list[UpstreamUncovered]


class UpstreamForming(BaseModel):
    """The period market-data is building right now, or the reason there is none.

    `state` is the field this exists for: `forming`, `not_tracked`, `market_closed` or
    `no_quotes`. A nullable candle would collapse the last three, and they are the whole
    difference between "the market is shut" and "collection has stopped".
    """

    symbol: str
    resolution: str | None = None
    state: str
    candle: UpstreamCandle | None = None
    market_open: bool | None = None


class UpstreamCoverageRange(BaseModel):
    from_: datetime = Field(alias="from")
    to: datetime
    history_ended: bool


class UpstreamCoverage(BaseModel):
    symbol: str
    resolution: str
    ranges: list[UpstreamCoverageRange]
    earliest_reachable: datetime | None = None


class UpstreamInstrument(BaseModel):
    symbol: str
    name: str
    asset_class: str
    tradeable: bool
