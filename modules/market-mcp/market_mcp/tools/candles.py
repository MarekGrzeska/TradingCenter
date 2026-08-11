"""Candles, their shape over a window, and what the archive has verified."""

from __future__ import annotations

from datetime import UTC, datetime

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from .. import reduce, uncertainty
from ..client import UpstreamClient
from ..errors import ToolRefusal
from ..upstream import UpstreamCandles, UpstreamCoverage
from ._shared import READ_ONLY, is_tracked, raise_for_status, resolve_window

# design.md, "Sufity są liczbami w kodzie, nie wartościami w konfiguracji" — a ceiling
# that lived in .env would drift from the description a caller was given for it.
DEFAULT_CANDLE_TARGET = 200
REFUSE_ABOVE_CANDLES = DEFAULT_CANDLE_TARGET * 10  # 2000

COVERAGE_RANGE_LIMIT = 20


class CandleOut(BaseModel):
    time: datetime
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None


class GetCandlesOut(BaseModel):
    symbol: str
    resolution: str
    from_: datetime = Field(serialization_alias="from")
    to: datetime
    aggregated: bool = Field(
        description="true when each candle below covers more than one original period"
    )
    original_candle_count: int | None = Field(
        default=None, description="raw candle count before aggregation; null when not aggregated"
    )
    candles: list[CandleOut]
    notes: list[str] = Field(
        default_factory=list, description="uncovered ranges, a derived series, or why it is empty"
    )


class LastPriceOut(BaseModel):
    symbol: str
    resolution: str
    time: datetime | None = Field(
        default=None, description="null when the archive has no candle to answer with"
    )
    close: float | None = None
    age_seconds: float | None = Field(
        default=None, description="seconds since this candle's period started"
    )
    notes: list[str] = Field(default_factory=list)


class SummarizeRangeOut(BaseModel):
    symbol: str
    resolution: str
    from_: datetime = Field(serialization_alias="from")
    to: datetime
    candle_count: int
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    change: float | None = Field(default=None, description="close - open")
    change_percent: float | None = None
    avg_candle_range: float | None = Field(
        default=None, description="average high-low across candles in the window"
    )
    max_candle_range: float | None = None
    biggest_move: float | None = Field(
        default=None, description="largest single-candle close - open, signed"
    )
    biggest_move_at: datetime | None = None
    gap_count: int = Field(description="how many unverified stretches the window contains")
    notes: list[str] = Field(default_factory=list)


class CoverageRangeOut(BaseModel):
    from_: datetime = Field(serialization_alias="from")
    to: datetime
    history_ended: bool


class DescribeCoverageOut(BaseModel):
    symbol: str
    resolution: str
    ranges: list[CoverageRangeOut]
    earliest_reachable: datetime | None = None
    omitted_ranges: int = Field(
        default=0,
        description="verified ranges older than the ones shown, dropped to keep the reply short",
    )
    notes: list[str] = Field(default_factory=list)


def register(mcp: FastMCP, upstream: UpstreamClient) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def get_candles(
        symbol: str,
        resolution: str = "MINUTE",
        from_iso: str | None = None,
        to_iso: str | None = None,
    ) -> GetCandlesOut:
        """OHLC candles for one pair over a UTC time range, `from_iso`/`to_iso` in
        ISO-8601. Omit both bounds for the last day. Prices are the **bid** side —
        the only side the archive holds. A series larger than the ceiling comes back
        bucketed to roughly 200 candles rather than in full — each bucket then
        covers more than one original period, which `aggregated` and
        `original_candle_count` say.

        Refuses rather than aggregate a series so large the result would no longer
        answer what was asked (~2000 candles) — ask for a coarser resolution or a
        narrower window instead.
        """
        start, end = resolve_window(from_iso, to_iso)
        response = await upstream.get(
            f"/candles/{symbol}",
            params={"resolution": resolution, "from": start.isoformat(), "to": end.isoformat()},
        )
        await raise_for_status(response)
        parsed = UpstreamCandles.model_validate(response.json())

        raw = [c.model_dump() for c in parsed.candles]
        if len(raw) > REFUSE_ABOVE_CANDLES:
            raise ToolRefusal(
                f"{symbol} {resolution} over {start.isoformat()}..{end.isoformat()} is "
                f"{len(raw)} candles, above the {REFUSE_ABOVE_CANDLES}-candle ceiling "
                "for one reply. Ask for a coarser resolution or a narrower window."
            )

        notes: list[str] = []
        uncovered_note = uncertainty.uncovered_sentence([(u.from_, u.to) for u in parsed.uncovered])
        if uncovered_note:
            notes.append(uncovered_note)
        derived_note = uncertainty.derived_sentence(parsed.derived, resolution)
        if derived_note:
            notes.append(derived_note)
        if not raw:
            tracked = await is_tracked(upstream, symbol, resolution)
            notes.append(uncertainty.empty_series_sentence(symbol, tracked))

        aggregated_candles, agg = reduce.aggregate_candles(raw, DEFAULT_CANDLE_TARGET)
        if agg is not None:
            notes.append(
                f"Aggregated {agg.original_count} candles into "
                f"{len(aggregated_candles)}, each covering {agg.bucket_span} original "
                "periods."
            )

        return GetCandlesOut(
            symbol=symbol,
            resolution=resolution,
            from_=start,
            to=end,
            aggregated=agg is not None,
            original_candle_count=agg.original_count if agg else None,
            candles=[CandleOut(**c) for c in aggregated_candles],
            notes=notes,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def get_last_price(symbol: str, resolution: str = "MINUTE") -> LastPriceOut:
        """The most recent candle for a pair, with its moment (UTC) and its age in
        seconds — a price with no age attached could be from now or from Friday's
        close, and there is no way to tell which from the number alone. The price is
        the **bid** side, the only side the archive holds.
        """
        start, end = resolve_window(None, None)
        response = await upstream.get(
            f"/candles/{symbol}",
            params={"resolution": resolution, "from": start.isoformat(), "to": end.isoformat()},
        )
        await raise_for_status(response)
        parsed = UpstreamCandles.model_validate(response.json())

        notes: list[str] = []
        derived_note = uncertainty.derived_sentence(parsed.derived, resolution)
        if derived_note:
            notes.append(derived_note)

        if not parsed.candles:
            tracked = await is_tracked(upstream, symbol, resolution)
            notes.append(uncertainty.empty_series_sentence(symbol, tracked))
            return LastPriceOut(symbol=symbol, resolution=resolution, notes=notes)

        latest = parsed.candles[-1]
        age_seconds = (datetime.now(UTC) - latest.time).total_seconds()
        return LastPriceOut(
            symbol=symbol,
            resolution=resolution,
            time=latest.time,
            close=latest.close,
            age_seconds=age_seconds,
            notes=notes,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def summarize_range(
        symbol: str,
        resolution: str = "MINUTE",
        from_iso: str | None = None,
        to_iso: str | None = None,
    ) -> SummarizeRangeOut:
        """A window's shape in a dozen numbers instead of its candles: total change,
        how choppy it was, its single biggest move and when. `from_iso`/`to_iso` are
        UTC, ISO-8601; omit both for the last day. Prices are the **bid** side. For
        "what happened here" rather than "draw me the chart" — read `get_candles` for
        the series itself.
        """
        start, end = resolve_window(from_iso, to_iso)
        response = await upstream.get(
            f"/candles/{symbol}",
            params={"resolution": resolution, "from": start.isoformat(), "to": end.isoformat()},
        )
        await raise_for_status(response)
        parsed = UpstreamCandles.model_validate(response.json())

        notes: list[str] = []
        uncovered_note = uncertainty.uncovered_sentence([(u.from_, u.to) for u in parsed.uncovered])
        if uncovered_note:
            notes.append(uncovered_note)
        derived_note = uncertainty.derived_sentence(parsed.derived, resolution)
        if derived_note:
            notes.append(derived_note)

        candles = parsed.candles
        if not candles:
            tracked = await is_tracked(upstream, symbol, resolution)
            notes.append(uncertainty.empty_series_sentence(symbol, tracked))
            return SummarizeRangeOut(
                symbol=symbol,
                resolution=resolution,
                from_=start,
                to=end,
                candle_count=0,
                gap_count=len(parsed.uncovered),
                notes=notes,
            )

        ranges = [c.high - c.low for c in candles if c.high is not None and c.low is not None]
        moves = [
            (c.time, c.close - c.open)
            for c in candles
            if c.open is not None and c.close is not None
        ]
        open_ = next((c.open for c in candles if c.open is not None), None)
        close_ = next((c.close for c in reversed(candles) if c.close is not None), None)
        highs = [c.high for c in candles if c.high is not None]
        lows = [c.low for c in candles if c.low is not None]

        change = close_ - open_ if (open_ is not None and close_ is not None) else None
        change_percent = change / open_ * 100 if (change is not None and open_) else None
        biggest = max(moves, key=lambda pair: abs(pair[1])) if moves else None

        return SummarizeRangeOut(
            symbol=symbol,
            resolution=resolution,
            from_=start,
            to=end,
            candle_count=len(candles),
            open=open_,
            high=max(highs) if highs else None,
            low=min(lows) if lows else None,
            close=close_,
            change=change,
            change_percent=change_percent,
            avg_candle_range=(sum(ranges) / len(ranges)) if ranges else None,
            max_candle_range=max(ranges) if ranges else None,
            biggest_move=biggest[1] if biggest else None,
            biggest_move_at=biggest[0] if biggest else None,
            gap_count=len(parsed.uncovered),
            notes=notes,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def describe_coverage(symbol: str, resolution: str = "MINUTE") -> DescribeCoverageOut:
        """What the archive has actually verified for one pair: the ranges it looked
        at (UTC instants) — even ones with no candle in them — and how far back it
        has confirmed the provider's own history reaches. Up to 20 ranges, most
        recent first; older ones are counted in `omitted_ranges`, not dropped
        silently.
        """
        response = await upstream.get(f"/coverage/{symbol}", params={"resolution": resolution})
        await raise_for_status(response)
        parsed = UpstreamCoverage.model_validate(response.json())

        notes: list[str] = []
        if not parsed.ranges:
            tracked = await is_tracked(upstream, symbol, resolution)
            notes.append(uncertainty.empty_series_sentence(symbol, tracked))

        ordered = sorted(parsed.ranges, key=lambda r: r.to, reverse=True)
        kept, dropped = reduce.truncate(ordered, COVERAGE_RANGE_LIMIT)
        if dropped:
            notes.append(
                f"{dropped} older verified range(s) omitted; showing the "
                f"{COVERAGE_RANGE_LIMIT} most recent."
            )

        return DescribeCoverageOut(
            symbol=symbol,
            resolution=resolution,
            ranges=[
                CoverageRangeOut(from_=r.from_, to=r.to, history_ended=r.history_ended)
                for r in kept
            ],
            earliest_reachable=parsed.earliest_reachable,
            omitted_ranges=dropped,
            notes=notes,
        )
