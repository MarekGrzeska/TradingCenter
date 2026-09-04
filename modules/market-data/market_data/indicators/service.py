"""Indicators: a catalogue anyone can build a picker from, and a computation over the series this
module owns. An indicator measures, it never decides. Two callers now, so refusals are raised."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Sequence
from datetime import UTC, datetime

import numpy as np

from ..contract import (
    IndicatorCatalogueEntryOut,
    IndicatorLevelOut,
    IndicatorLineSpecOut,
    IndicatorMarkerOut,
    IndicatorParamOut,
    IndicatorRenderOut,
    IndicatorResultOut,
    IndicatorsCatalogueOut,
    IndicatorsOut,
    IndicatorsRequest,
    IndicatorZoneOut,
    Uncovered,
)
from ..coverage import uncovered_within
from ..models import Candle, PriceSide, Resolution
from ..periods import period_length, periods_between
from ..rollups import DERIVABLE, DerivedCandle, read_derived
from ..store import read_candles
from .catalogue import (
    ALGORITHM_VERSION,
    CATALOGUE,
    ClusterLevels,
    HtfLevels,
    IndicatorSpec,
    Lines,
    Markers,
    MinuteZones,
    ParamOutOfRange,
    Series,
    TimeProfile,
    UnknownIndicator,
    Zone,
    Zones,
)
from .catalogue import get as get_indicator

# candles × requested indicators, above which the module refuses rather than compute. Re-measured
# in 2.17 against the full 44-entry catalogue: ~63ms p95 at ~4500 candles, so the number held.
REQUEST_CEILING = 200_000

# The resolution a few entries read regardless of what was requested. Raw MINUTE is finer on paper,
# but nothing here tracks it — pairs are collected starting at MINUTE_5.
FINE_RESOLUTION = Resolution.MINUTE_5

class IndicatorRequestRejected(ValueError):
    """The request is the thing that is wrong, not the archive. Raised rather than returned so neither
    caller can forget it: a 422 there, a tool refusal here."""


def _ensure_utc(value: datetime) -> datetime:
    # A naive instant is read as UTC rather than refused, matching `candles.py`'s
    # `_window` — the commonest way to write one by hand, and the archive stores instants.
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _render_out(entry: IndicatorSpec) -> IndicatorRenderOut:
    return IndicatorRenderOut(
        pane=entry.render.pane,
        style=entry.render.style,
        scale=entry.render.scale,
        autoscale=entry.render.autoscale,
        range=entry.render.range,
        levels=list(entry.render.levels),
    )


def _entry_out(entry: IndicatorSpec) -> IndicatorCatalogueEntryOut:
    return IndicatorCatalogueEntryOut(
        id=entry.id,
        name=entry.name,
        aliases=list(entry.aliases),
        group=entry.group,
        output=entry.output,
        params=[
            IndicatorParamOut(name=p.name, type=p.type, default=p.default, min=p.min, max=p.max)
            for p in entry.params
        ],
        lines=[
            IndicatorLineSpecOut(key=line.key, label=line.label, style=line.style)
            for line in entry.lines
        ],
        render=_render_out(entry),
        warmup_kind=entry.warmup.kind,
    )


def catalogue() -> IndicatorsCatalogueOut:
    """Every indicator this module can compute, and how to draw it. A consumer builds its whole picker
    from this and never needs to know an indicator by name beforehand."""
    return IndicatorsCatalogueOut(
        algorithm_version=ALGORITHM_VERSION,
        indicators=[_entry_out(entry) for entry in CATALOGUE],
    )


async def compute(symbol: str, body: IndicatorsRequest, db, limiter) -> IndicatorsOut:
    """Compute one or more indicators over a range, on one shared time axis. Reads further back than
    `from` by each indicator's warmup, and says whether the archive held enough for that."""
    start = _ensure_utc(body.from_)
    end = _ensure_utc(body.to)
    if end < start:
        raise IndicatorRequestRejected(
            f"`to` is before `from`: {start.isoformat()} to {end.isoformat()}"
        )

    resolved: list[tuple[IndicatorSpec, dict[str, float]]] = []
    for spec_in in body.specs:
        try:
            entry = get_indicator(spec_in.id)
        except UnknownIndicator:
            raise IndicatorRequestRejected(f"unknown indicator: {spec_in.id!r}") from None
        try:
            params = entry.resolve_params(spec_in.params)
        except ParamOutOfRange as err:
            raise IndicatorRequestRejected(str(err)) from None
        resolved.append((entry, params))

    requested_candles = periods_between(body.resolution, start, end)
    cells = requested_candles * len(resolved)
    if cells > REQUEST_CEILING:
        raise IndicatorRequestRejected(
            f"request exceeds the indicator ceiling of {REQUEST_CEILING} "
            f"candles×indicators (~{cells} asked for)"
        )

    max_warmup_bars = max((entry.warmup_bars(params) for entry, params in resolved), default=0)
    extended_start = start - max_warmup_bars * period_length(body.resolution)

    needed_htf_resolutions = {
        entry.higher_resolution
        for entry, _params in resolved
        if entry.higher_resolution is not None
    }
    needs_minute_series = any(entry.needs_minute_series for entry, _params in resolved)
    # A DAY-resolution chart asking for `time_profile` would otherwise hide a fine-resolution read
    # orders of magnitude bigger than the one the ceiling above priced.
    if needs_minute_series and body.resolution not in (Resolution.MINUTE, FINE_RESOLUTION):
        fine_candles = periods_between(FINE_RESOLUTION, start, end)
        if fine_candles > REQUEST_CEILING:
            raise IndicatorRequestRejected(
                f"the {FINE_RESOLUTION.value} series time_profile/session_range/"
                f"opening_range need exceeds the indicator ceiling of "
                f"{REQUEST_CEILING} candles (~{fine_candles} asked for)"
            )

    # Keyed by the resolution that could not be read, not by entry: three session windows
    # and the time profile all want the same fine series and all get the same reason.
    missing_series: dict[Resolution, str] = {}

    async with limiter, db.acquire() as conn:
        rows: Sequence[Candle | DerivedCandle] = await read_candles(
            conn, symbol, body.resolution, extended_start, end
        )
        derived = False
        if not rows and body.resolution in DERIVABLE:
            rows = await read_derived(conn, symbol, body.resolution, extended_start, end)
            derived = True
        gaps = await uncovered_within(conn, symbol, body.resolution, start, end)

        first_requested = 0
        while first_requested < len(rows) and rows[first_requested].period_start < start:
            first_requested += 1

    # A series the archive does not hold is not the caller's mistake. The miss is written down here
    # and handed to whichever entries asked for that series, rather than taking the request down.
        htf_periods: dict[Resolution, list[tuple[datetime, Candle]]] = {}
        for htf_resolution in needed_htf_resolutions:
            htf_window_start = start - period_length(htf_resolution)
            htf_candles = await read_candles(conn, symbol, htf_resolution, htf_window_start, end)
            if not htf_candles:
                missing_series[htf_resolution] = (
                    f"no {htf_resolution.value} series collected for {symbol!r}; "
                    "htf_levels/pivots need it read at that resolution directly"
                )
                continue
            htf_periods[htf_resolution] = _htf_effective_periods(htf_candles, start, end)

        minute_rows: Sequence[Candle | DerivedCandle] = []
        if needs_minute_series:
            # Trimmed to exactly `[start, end)` even when `rows` is sitting right there: `rows` may
            # reach back for another entry's warmup, and none of these entries warms up.
            if body.resolution in (Resolution.MINUTE, FINE_RESOLUTION):
                minute_rows = rows[first_requested:]
            else:
                minute_rows = await read_candles(conn, symbol, FINE_RESOLUTION, start, end)
                if not minute_rows and FINE_RESOLUTION in DERIVABLE:
                    minute_rows = await read_derived(conn, symbol, FINE_RESOLUTION, start, end)
            if not minute_rows:
                missing_series[FINE_RESOLUTION] = (
                    f"no {FINE_RESOLUTION.value} series collected for {symbol!r}, and "
                    "none could be derived from MINUTE either; time_profile/session_range/"
                    "opening_range need one of those two read directly"
                )

    available_warmup_bars = first_requested
    times_all = [row.period_start for row in rows]

    # The arithmetic runs on a worker thread: numpy and TA-Lib hold the interpreter for tens of
    # milliseconds over a few thousand candles, and this loop also serves the candle stream.
    results = await asyncio.to_thread(
        _compute_results,
        resolved,
        rows,
        times_all,
        minute_rows,
        body.resolution,
        gaps,
        available_warmup_bars,
        first_requested,
        htf_periods,
        start,
        missing_series,
    )

    return IndicatorsOut(
        symbol=symbol,
        resolution=body.resolution,
        price_side=PriceSide.BID,
        derived=derived,
        algorithm_version=ALGORITHM_VERSION,
        times=times_all[first_requested:],
        warmup_from=rows[0].period_start if rows else None,
        uncovered=[Uncovered(from_=gap_start, to=gap_end) for gap_start, gap_end in gaps],
        results=results,
    )


def _compute_results(
    resolved: Sequence[tuple[IndicatorSpec, dict[str, float]]],
    rows: Sequence[Candle | DerivedCandle],
    times_all: Sequence[datetime],
    minute_rows: Sequence[Candle | DerivedCandle],
    resolution: Resolution,
    gaps: Sequence[tuple[datetime, datetime]],
    available_warmup_bars: int,
    first_requested: int,
    htf_periods: dict[Resolution, list[tuple[datetime, Candle]]],
    start: datetime,
    missing_series: dict[Resolution, str],
) -> list[IndicatorResultOut]:
    """Everything after the reads and before the response: pure, synchronous, and therefore the part
    that runs off the event loop."""
    series = _build_series(rows)
    session_close_before = _session_close_before(times_all, resolution, gaps)
    minute_series = _build_series(minute_rows) if minute_rows else None
    minute_times = [row.period_start for row in minute_rows] if minute_rows else None
    return [
        _result_out(
            entry,
            params,
            series,
            times_all,
            available_warmup_bars,
            first_requested,
            htf_periods,
            session_close_before,
            minute_series,
            minute_times,
            start,
            missing_series,
        )
        for entry, params in resolved
    ]


def _build_series(rows: Sequence[Candle | DerivedCandle]) -> Series:
    def column(field: str) -> np.ndarray:
        return np.array(
            [np.nan if (v := getattr(row, field)) is None else v for row in rows],
            dtype=np.float64,
        )

    return Series(open=column("open"), high=column("high"), low=column("low"), close=column("close"))


def _session_close_before(
    times: Sequence[datetime],
    resolution: Resolution,
    gaps: Sequence[tuple[datetime, datetime]],
) -> np.ndarray:
    """`out[i]` is true when the stretch before bar `i` is wider than a period *and* the archive has
    verified it — a shut market, as opposed to a hole nobody has looked at yet."""
    n = len(times)
    out = np.zeros(n, dtype=bool)
    if n < 2:
        return out
    step = period_length(resolution)
    for i in range(1, n):
        if times[i] - times[i - 1] <= step:
            continue
        overlaps_uncovered = any(
            gap_start < times[i] and gap_end > times[i - 1] for gap_start, gap_end in gaps
        )
        out[i] = not overlaps_uncovered
    return out


def _zone_out(zone: Zone, times: Sequence[datetime]) -> IndicatorZoneOut:
    return IndicatorZoneOut(
        from_=times[zone.start_bar],
        to=times[zone.end_bar] if zone.end_bar is not None else None,
        top=zone.top,
        bottom=zone.bottom,
        direction=zone.direction,
        touched_at=times[zone.touched_at_bar] if zone.touched_at_bar is not None else None,
        filled_at=times[zone.filled_at_bar] if zone.filled_at_bar is not None else None,
    )


def _htf_effective_periods(
    htf_candles: Sequence[Candle], start: datetime, end: datetime
) -> list[tuple[datetime, Candle]]:
    """Which of a higher-resolution read's closed candles are in effect in `[start, end)`. A candle's
    close is the next candle's `period_start`, read rather than assumed; the newest is estimated."""
    if not htf_candles:
        return []
    step = period_length(htf_candles[0].resolution)
    closings: list[tuple[datetime, Candle]] = []
    for i, row in enumerate(htf_candles):
        close_moment = (
            htf_candles[i + 1].period_start if i + 1 < len(htf_candles) else row.period_start + step
        )
        if close_moment <= end:
            closings.append((close_moment, row))
    closings.sort(key=lambda pair: pair[0])

    kept = [pair for pair in closings if pair[0] > start]
    prior = [pair for pair in closings if pair[0] <= start]
    if prior:
        kept = [prior[-1], *kept]
    return kept


def _result_out(
    entry: IndicatorSpec,
    params: dict[str, float],
    series: Series,
    times_all: Sequence[datetime],
    available_warmup_bars: int,
    first_requested: int,
    htf_periods: dict[Resolution, list[tuple[datetime, Candle]]],
    session_close_before: np.ndarray,
    minute_series: Series | None,
    minute_times: list[datetime] | None,
    requested_start: datetime,
    missing_series: dict[Resolution, str],
) -> IndicatorResultOut:
    needed = entry.warmup_bars(params)
    settled = available_warmup_bars >= needed

    # Asked for before anything is computed: an entry whose series is missing has no answer, and the
    # reason belongs where its answer would have been. Both series are checked, not the likelier one.
    wanted = (
        FINE_RESOLUTION if entry.needs_minute_series else None,
        entry.higher_resolution,
    )
    for resolution in wanted:
        if resolution is not None and resolution in missing_series:
            return IndicatorResultOut(
                id=entry.id, params=params, settled=False, error=missing_series[resolution]
            )

    # One case per computer, and the computer says which. A chain of `if ... is not None` made branch
    # order the tie-break for an entry that set two; a `match` has no order to get wrong.
    match entry.computer:
        case Zones(fn=compute):
            zones = [
                _zone_out(zone, times_all)
                for zone in compute(series, params, session_close_before)
                if zone.start_bar >= first_requested
            ]
            return IndicatorResultOut(
                id=entry.id, params=params, warmup_bars=needed, settled=settled, zones=zones
            )

        case MinuteZones(fn=compute):
            assert minute_series is not None and minute_times is not None, entry.id
            zones = [
                _zone_out(zone, minute_times)
                for zone in compute(minute_series, minute_times, params)
            ]
            return IndicatorResultOut(
                id=entry.id, params=params, warmup_bars=0, settled=True, zones=zones
            )

        case TimeProfile(fn=compute):
            assert minute_series is not None and minute_times is not None, entry.id
            profile_levels = [
                IndicatorLevelOut(
                    from_=requested_start, price=level.price, label=level.label, count=level.count
                )
                for level in compute(minute_series, minute_times, params)
            ]
            return IndicatorResultOut(
                id=entry.id, params=params, warmup_bars=0, settled=True, levels=profile_levels
            )

        case HtfLevels(fn=compute, resolution=resolution):
            levels: list[IndicatorLevelOut] = []
            for close_moment, candle in htf_periods.get(resolution, []):
                if (
                    candle.open is None
                    or candle.high is None
                    or candle.low is None
                    or candle.close is None
                ):
                    continue
                ohlc = (candle.open, candle.high, candle.low, candle.close)
                levels.extend(
                    IndicatorLevelOut(from_=close_moment, price=level.price, label=level.label)
                    for level in compute(ohlc)
                )
            return IndicatorResultOut(
                id=entry.id, params=params, warmup_bars=0, settled=True, levels=levels
            )

        case Markers(fn=compute):
            markers = [
                IndicatorMarkerOut(time=times_all[point.bar], label=point.label, price=point.price)
                for point in compute(series, params)
                if point.bar >= first_requested
            ]
            return IndicatorResultOut(
                id=entry.id, params=params, warmup_bars=needed, settled=settled, markers=markers
            )

        case ClusterLevels(fn=compute):
            levels = [
                IndicatorLevelOut(
                    from_=times_all[cluster.bar],
                    price=cluster.price,
                    label=cluster.label,
                    count=cluster.count,
                )
                for cluster in compute(series, params)
                if cluster.bar >= first_requested
            ]
            return IndicatorResultOut(
                id=entry.id, params=params, warmup_bars=needed, settled=settled, levels=levels
            )

        case Lines(fn=compute):
            values = compute(series, params)
            lines = {
                key: [None if math.isnan(v) else float(v) for v in arr[first_requested:]]
                for key, arr in values.items()
            }
            return IndicatorResultOut(
                id=entry.id,
                params=params,
                warmup_bars=needed,
                settled=settled,
                lines=lines,
            )
