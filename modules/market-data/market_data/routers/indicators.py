"""Wskaźniki: a catalogue anyone can build a picker from, and a computation over the
series this module already owns.

The one rule every line here answers to: a wskaźnik measures, it never orzeka
(`market-data-indicators` spec, "Katalog mierzy, a nie orzeka"). Nothing in this router
returns a boolean, and every threshold a formula needs is a parameter the caller sent
back to it in the response — never a constant this file decided on its own.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import UTC, datetime

import numpy as np
from fastapi import APIRouter, Depends, HTTPException

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
    Problem,
    Uncovered,
)
from ..coverage import uncovered_within
from ..indicators.catalogue import (
    ALGORITHM_VERSION,
    CATALOGUE,
    IndicatorSpec,
    ParamOutOfRange,
    Series,
    UnknownIndicator,
)
from ..indicators.catalogue import get as get_indicator
from ..models import Candle, PriceSide, Resolution
from ..periods import period_length, periods_between
from ..rollups import DERIVABLE, DerivedCandle, read_derived
from ..store import read_candles
from .deps import indicator_limiter, pool

# candles × requested wskaźniki, above which the module refuses rather than compute.
# Set in etap zero at 5000 candles × 10 wskaźniki, ~16.5ms p95 on a 3-entry catalogue.
# Re-measured in 2.17 against the full 44-entry catalogue E1 grew it to: every entry at
# once, at however many candles this ceiling allows that many entries (~4500), costs
# ~63ms p95 (`test_indicators_performance.py`) — cells scale roughly linearly with
# either factor, so the number held rather than needing to move
# (design.md, "Obliczenia dzielą pętlę zdarzeń ze strumieniem świec").
REQUEST_CEILING = 200_000

router = APIRouter()


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


@router.get(
    "/indicators",
    tags=["indicators"],
    response_model=IndicatorsCatalogueOut,
    summary="Every wskaźnik this module can compute, and how to draw it",
    description=(
        "A consumer builds its whole picker from this — parameters, defaults, output "
        "shape, render hint — and never needs to know a wskaźnik by name beforehand."
    ),
)
async def catalogue() -> IndicatorsCatalogueOut:
    return IndicatorsCatalogueOut(
        algorithm_version=ALGORITHM_VERSION,
        indicators=[_entry_out(entry) for entry in CATALOGUE],
    )


@router.post(
    "/indicators/{symbol}",
    tags=["indicators"],
    response_model=IndicatorsOut,
    responses={422: {"model": Problem}},
    summary="Compute one or more wskaźniki over a range, on one shared time axis",
    description=(
        "Reads further back than `from` on its own, by however much each requested "
        "wskaźnik's warmup needs, and says in `warmup_from`/`settled` whether the "
        "archive actually held enough history for the answer to be trusted."
    ),
)
async def compute(
    symbol: str,
    body: IndicatorsRequest,
    db=Depends(pool),
    limiter=Depends(indicator_limiter),
) -> IndicatorsOut:
    start = _ensure_utc(body.from_)
    end = _ensure_utc(body.to)
    if end < start:
        raise HTTPException(
            status_code=422,
            detail=f"`to` is before `from`: {start.isoformat()} to {end.isoformat()}",
        )

    resolved: list[tuple[IndicatorSpec, dict[str, float]]] = []
    for spec_in in body.specs:
        try:
            entry = get_indicator(spec_in.id)
        except UnknownIndicator:
            raise HTTPException(status_code=422, detail=f"unknown indicator: {spec_in.id!r}") from None
        try:
            params = entry.resolve_params(spec_in.params)
        except ParamOutOfRange as err:
            raise HTTPException(status_code=422, detail=str(err)) from None
        resolved.append((entry, params))

    requested_candles = periods_between(body.resolution, start, end)
    cells = requested_candles * len(resolved)
    if cells > REQUEST_CEILING:
        raise HTTPException(
            status_code=422,
            detail=(
                f"request exceeds the indicator ceiling of {REQUEST_CEILING} "
                f"candles×indicators (~{cells} asked for)"
            ),
        )

    max_warmup_bars = max((entry.warmup_bars(params) for entry, params in resolved), default=0)
    extended_start = start - max_warmup_bars * period_length(body.resolution)

    needed_htf_resolutions = {
        entry.higher_resolution
        for entry, _params in resolved
        if entry.higher_resolution is not None
    }

    async with limiter, db.acquire() as conn:
        rows: Sequence[Candle | DerivedCandle] = await read_candles(
            conn, symbol, body.resolution, extended_start, end
        )
        derived = False
        if not rows and body.resolution in DERIVABLE:
            rows = await read_derived(conn, symbol, body.resolution, extended_start, end)
            derived = True
        gaps = await uncovered_within(conn, symbol, body.resolution, start, end)

        htf_periods: dict[Resolution, list[tuple[datetime, Candle]]] = {}
        for htf_resolution in needed_htf_resolutions:
            htf_window_start = start - period_length(htf_resolution)
            htf_candles = await read_candles(conn, symbol, htf_resolution, htf_window_start, end)
            if not htf_candles:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"no {htf_resolution.value} series collected for {symbol!r}; "
                        "htf_levels/pivots need it read at that resolution directly"
                    ),
                )
            htf_periods[htf_resolution] = _htf_effective_periods(htf_candles, start, end)

    first_requested = 0
    while first_requested < len(rows) and rows[first_requested].period_start < start:
        first_requested += 1
    available_warmup_bars = first_requested

    series = _build_series(rows)
    times_all = [row.period_start for row in rows]

    results = [
        _result_out(
            entry, params, series, times_all, available_warmup_bars, first_requested, htf_periods
        )
        for entry, params in resolved
    ]

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


def _build_series(rows: Sequence[Candle | DerivedCandle]) -> Series:
    def column(field: str) -> np.ndarray:
        return np.array(
            [np.nan if (v := getattr(row, field)) is None else v for row in rows],
            dtype=np.float64,
        )

    return Series(open=column("open"), high=column("high"), low=column("low"), close=column("close"))


def _htf_effective_periods(
    htf_candles: Sequence[Candle], start: datetime, end: datetime
) -> list[tuple[datetime, Candle]]:
    """Which of a higher-resolution read's closed candles are in effect somewhere in
    `[start, end)` — a candle's own close moment is the *next* candle's `period_start`,
    read from the data rather than assumed (`DAY`/`WEEK` follow the venue's session,
    not a fixed number of seconds — `rollups.py`'s reason for never flooring either).
    The newest read candle has no next one to read that from, so its close is estimated
    as one period-length later, the same safe-overstatement `periods.py` already uses
    for sizing.

    Kept to one candle per boundary crossed, plus the single one already in effect at
    `start` — enough to draw an unbroken ray across the whole requested window without
    the list growing with everything the archive has ever collected.
    """
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
) -> IndicatorResultOut:
    needed = entry.warmup_bars(params)
    settled = available_warmup_bars >= needed

    if entry.higher_resolution is not None:
        assert entry.compute_htf_levels is not None, entry.id
        levels: list[IndicatorLevelOut] = []
        for close_moment, candle in htf_periods.get(entry.higher_resolution, []):
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
                for level in entry.compute_htf_levels(ohlc)
            )
        return IndicatorResultOut(
            id=entry.id, params=params, warmup_bars=0, settled=True, levels=levels
        )

    if entry.output == "markers":
        assert entry.compute_markers is not None, entry.id
        markers = [
            IndicatorMarkerOut(time=times_all[point.bar], label=point.label, price=point.price)
            for point in entry.compute_markers(series, params)
            if point.bar >= first_requested
        ]
        return IndicatorResultOut(
            id=entry.id, params=params, warmup_bars=needed, settled=settled, markers=markers
        )

    if entry.output == "levels":
        assert entry.compute_cluster_levels is not None, entry.id
        levels = [
            IndicatorLevelOut(
                from_=times_all[cluster.bar],
                price=cluster.price,
                label=cluster.label,
                count=cluster.count,
            )
            for cluster in entry.compute_cluster_levels(series, params)
            if cluster.bar >= first_requested
        ]
        return IndicatorResultOut(
            id=entry.id, params=params, warmup_bars=needed, settled=settled, levels=levels
        )

    values = entry.compute(series, params)
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
