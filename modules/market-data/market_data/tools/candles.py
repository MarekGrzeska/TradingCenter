"""Candles, their shape over a window, and what the archive has verified."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from ..models import Candle
from ..reads import FormingState, Series, read_forming, read_pair_coverage, read_series
from ..rollups import DerivedCandle
from . import reduce, uncertainty
from ._shared import (
    READ_ONLY,
    ToolContext,
    WindowedOut,
    is_tracked,
    resolution_of,
    resolve_window,
    tracked_pair,
    tracked_resolutions,
)
from .errors import ToolRefusal

# design.md, "Sufity są liczbami w kodzie, nie wartościami w konfiguracji" — a ceiling
# that lived in .env would drift from the description a caller was given for it.
DEFAULT_CANDLE_TARGET = 200
REFUSE_ABOVE_CANDLES = DEFAULT_CANDLE_TARGET * 10  # 2000

COVERAGE_RANGE_LIMIT = 20


# No `volume`: this archive's provider is a CFD feed, so the figure is not reliable
# enough to reason from and not worth its tokens in every candle.
class CandleOut(BaseModel):
    time: datetime
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None


class GetCandlesOut(WindowedOut):
    symbol: str
    resolution: str
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
    resolution: str | None = Field(
        default=None,
        description=(
            "which resolution this price came from; may differ from the one asked for "
            "when none was, and null when the archive had nothing to answer with"
        ),
    )
    time: datetime | None = Field(
        default=None, description="null when the archive has no candle to answer with"
    )
    close: float | None = None
    age_seconds: float | None = Field(
        default=None, description="seconds since this candle's period started"
    )
    forming: bool = Field(
        default=False,
        description=(
            "true when this period has not closed: the price is current, and its high, "
            "low and volume will still move"
        ),
    )
    market_open: bool | None = Field(
        default=None, description="null when the archive could not find out — not 'closed'"
    )
    notes: list[str] = Field(default_factory=list)


class SummarizeRangeOut(WindowedOut):
    symbol: str
    resolution: str
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


class CoverageRangeOut(WindowedOut):
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


def _rows(candles: Sequence[Candle | DerivedCandle]) -> list[dict]:
    """The four edges and the instant, as the reduction expects them.

    `time` rather than `period_start`: the reduction and every model here speak the wire's
    word for it, and a candle carries a dozen fields a model has no use for.
    """
    return [
        {
            "time": candle.period_start,
            "open": candle.open,
            "high": candle.high,
            "low": candle.low,
            "close": candle.close,
        }
        for candle in candles
    ]


async def _read_window(
    ctx: ToolContext, symbol: str, resolution: str, start: datetime, end: datetime
) -> Series:
    async with ctx.pool.acquire() as conn:
        return await read_series(conn, symbol, resolution_of(resolution), start, end)


async def _newest_candle(
    ctx: ToolContext, symbol: str, resolution: str, notes: list[str]
) -> Series:
    """The archive's newest candle for a pair, read at the instant the pair's own row
    reports for it rather than found by widening a window. Appends the sentence that says
    which kind of empty this is when there is nothing to read.
    """
    row = await tracked_pair(ctx, symbol, resolution)
    newest = row.latest_candle if row else None
    empty = Series(candles=[], derived=False, uncovered=[])
    if newest is None:
        notes.append(uncertainty.empty_series_sentence(symbol, row is not None))
        return empty

    # The read is exclusive at the top, so a second past the candle's own instant is the
    # narrowest range that contains it.
    series = await _read_window(ctx, symbol, resolution, newest, newest + timedelta(seconds=1))
    if not series.candles:
        notes.append(uncertainty.empty_series_sentence(symbol, True))
    return series


def register(mcp: FastMCP, ctx: ToolContext) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def get_candles(
        symbol: str,
        resolution: str = "MINUTE",
        from_iso: str | None = None,
        to_iso: str | None = None,
    ) -> GetCandlesOut:
        """OHLC candles for one pair over a UTC time range, `from_iso`/`to_iso` in
        ISO-8601; omit both bounds for the last day. Prices are the **bid** side, the
        only side the archive holds.

        A series larger than the ceiling comes back bucketed to roughly 200 candles, each
        bucket covering more than one period — `aggregated` and `original_candle_count`
        say so. Past ~2000 candles it refuses rather than answer something other than what
        was asked: ask for a coarser resolution or a narrower window.
        """
        start, end = resolve_window(from_iso, to_iso)
        series = await _read_window(ctx, symbol, resolution, start, end)

        raw = _rows(series.candles)
        if len(raw) > REFUSE_ABOVE_CANDLES:
            raise ToolRefusal(
                f"{symbol} {resolution} over {start.isoformat()}..{end.isoformat()} is "
                f"{len(raw)} candles, above the {REFUSE_ABOVE_CANDLES}-candle ceiling "
                "for one reply. Ask for a coarser resolution or a narrower window."
            )

        notes: list[str] = []
        uncovered_note = uncertainty.uncovered_sentence(list(series.uncovered))
        if uncovered_note:
            notes.append(uncovered_note)
        derived_note = uncertainty.derived_sentence(series.derived, resolution)
        if derived_note:
            notes.append(derived_note)
        if not raw:
            tracked = await is_tracked(ctx, symbol, resolution)
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
    async def get_last_price(symbol: str, resolution: str | None = None) -> LastPriceOut:
        """What a pair costs **now**: the period being built while the market trades, the
        last one that closed once it stops. `forming` says which — a forming period's high
        and low are not its range yet and will still move.

        Omit `resolution` and the archive answers from the finest one actually receiving
        quotes, which is not always the finest one tracked; the reply says which it used.
        Carries the candle's moment (UTC) and its age in seconds, because a price with no
        age could be from this second or from Friday's close. Prices are the **bid** side,
        the only side the archive holds.
        """
        async with ctx.pool.acquire() as conn:
            live = await read_forming(
                conn,
                ctx.hub,
                ctx.instruments,
                ctx.market_status,
                symbol,
                resolution_of(resolution) if resolution else None,
            )

        notes: list[str] = []
        if live.state is FormingState.FORMING and live.candle is not None:
            answered_with = live.resolution.value if live.resolution else None
            notes.append(uncertainty.forming_sentence(answered_with or "current"))
            return LastPriceOut(
                symbol=symbol,
                resolution=answered_with,
                time=live.candle.period_start,
                close=live.candle.close,
                age_seconds=(datetime.now(UTC) - live.candle.period_start).total_seconds(),
                forming=True,
                market_open=live.market_open,
                notes=notes,
            )

        notes.append(uncertainty.no_live_price_sentence(symbol, live.state.value, live.market_open))
        if live.state is FormingState.NOT_TRACKED:
            # Nothing is collected for this symbol at any resolution, so there is no
            # settled candle to fall back to either — and the sentence above already says
            # what to do about it.
            return LastPriceOut(symbol=symbol, resolution=resolution, notes=notes)

        settled_resolution = resolution or next(iter(await tracked_resolutions(ctx, symbol)), None)
        if settled_resolution is None:  # pragma: no cover - `not_tracked` covers this
            return LastPriceOut(symbol=symbol, resolution=None, notes=notes)

        series = await _newest_candle(ctx, symbol, settled_resolution, notes)
        derived_note = uncertainty.derived_sentence(series.derived, settled_resolution)
        if derived_note:
            notes.append(derived_note)

        if not series.candles:
            return LastPriceOut(
                symbol=symbol,
                resolution=settled_resolution,
                market_open=live.market_open,
                notes=notes,
            )

        latest = series.candles[-1]
        return LastPriceOut(
            symbol=symbol,
            resolution=settled_resolution,
            time=latest.period_start,
            close=latest.close,
            age_seconds=(datetime.now(UTC) - latest.period_start).total_seconds(),
            market_open=live.market_open,
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
        series = await _read_window(ctx, symbol, resolution, start, end)

        notes: list[str] = []
        uncovered_note = uncertainty.uncovered_sentence(list(series.uncovered))
        if uncovered_note:
            notes.append(uncovered_note)
        derived_note = uncertainty.derived_sentence(series.derived, resolution)
        if derived_note:
            notes.append(derived_note)

        candles = series.candles
        if not candles:
            tracked = await is_tracked(ctx, symbol, resolution)
            notes.append(uncertainty.empty_series_sentence(symbol, tracked))
            return SummarizeRangeOut(
                symbol=symbol,
                resolution=resolution,
                from_=start,
                to=end,
                candle_count=0,
                gap_count=len(series.uncovered),
                notes=notes,
            )

        ranges = [c.high - c.low for c in candles if c.high is not None and c.low is not None]
        moves = [
            (c.period_start, c.close - c.open)
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
            gap_count=len(series.uncovered),
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
        async with ctx.pool.acquire() as conn:
            found = await read_pair_coverage(conn, symbol, resolution_of(resolution))

        notes: list[str] = []
        if not found.ranges:
            tracked = await is_tracked(ctx, symbol, resolution)
            notes.append(uncertainty.empty_series_sentence(symbol, tracked))

        ordered = sorted(found.ranges, key=lambda r: r.range_end, reverse=True)
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
                CoverageRangeOut(
                    from_=r.range_start, to=r.range_end, history_ended=r.history_ended
                )
                for r in kept
            ],
            earliest_reachable=found.earliest_reachable,
            omitted_ranges=dropped,
            notes=notes,
        )
