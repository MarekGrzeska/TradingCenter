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
