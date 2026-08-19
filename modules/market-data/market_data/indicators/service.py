"""Indicators: a catalogue anyone can build a picker from, and a computation over the
series this module already owns.

The one rule every line here answers to: an indicator measures, it never decides
(`market-data-indicators` spec, "Katalog mierzy, a nie orzeka"). Nothing here returns a
boolean, and every threshold a formula needs is a parameter the caller sent back to it in
the response — never a constant this file decided on its own.

This was `routers/indicators.py` until the tool surface arrived. It has two callers now —
the REST route and the `/mcp` tools — so its refusals are raised as `IndicatorRequestRejected`
and each transport spells that in its own words: a 422 there, a tool refusal here.
"""

from __future__ import annotations

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

# candles × requested indicators, above which the module refuses rather than compute.
# Set in the first stage at 5000 candles × 10 indicators, ~16.5ms p95 on a 3-entry catalogue.
# Re-measured in 2.17 against the full 44-entry catalogue E1 grew it to: every entry at
# once, at however many candles this ceiling allows that many entries (~4500), costs
# ~63ms p95 (`test_indicators_performance.py`) — cells scale roughly linearly with
# either factor, so the number held rather than needing to move
# (design.md, "Obliczenia dzielą pętlę zdarzeń ze strumieniem świec").
REQUEST_CEILING = 200_000

# The resolution `time_profile`/`session_range_*`/`opening_range` read regardless of what
# was requested (`IndicatorSpec.needs_minute_series`). Raw MINUTE is the finer choice on
# paper, but nothing in this deployment actually tracks it — pairs are collected starting
# at MINUTE_5, with MINUTE itself existing only as the source `rollups.py` derives it from
# when asked for directly. Targeting MINUTE_5 here, with the same DERIVABLE fallback the
# primary series read already gets, is what makes these entries usable against real
# tracked pairs instead of refusing on every request for want of a series nobody collects.
FINE_RESOLUTION = Resolution.MINUTE_5

class IndicatorRequestRejected(ValueError):
    """The request is the thing that is wrong, not the archive.

    Raised rather than returned so neither caller can forget it: the REST route turns it
    into a 422, the tool surface into a refusal naming what to change.
    """


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
    """Every indicator this module can compute, and how to draw it.

    A consumer builds its whole picker from this — parameters, defaults, output shape,
    render hint — and never needs to know an indicator by name beforehand.
    """
    return IndicatorsCatalogueOut(
        algorithm_version=ALGORITHM_VERSION,
        indicators=[_entry_out(entry) for entry in CATALOGUE],
    )


async def compute(symbol: str, body: IndicatorsRequest, db, limiter) -> IndicatorsOut:
    """Compute one or more indicators over a range, on one shared time axis.

    Reads further back than `from` on its own, by however much each requested indicator's
    warmup needs, and says in `warmup_from`/`settled` whether the archive actually held
    enough history for the answer to be trusted.
    """
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
    # A DAY-resolution chart asking for `time_profile` can otherwise hide a
    # fine-resolution read many orders of magnitude bigger than what
    # `requested_candles` above ever saw — the module's one performance
    # promise (design.md, "Obliczenia dzielą pętlę zdarzeń ze strumieniem
    # świec") would not survive that read silently bypassing the ceiling.
    # Already covered when the chart itself reads at `FINE_RESOLUTION` or
    # finer (raw MINUTE): the top-level `cells` check above priced that read.
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

        # A series the archive does not hold is not the caller's mistake — it is a
        # property of what someone chose to collect, and it differs entry by entry. The
        # read still happens once per resolution rather than once per entry; what
        # changes is that a miss is written down here and handed to whichever entries
        # asked for that series, instead of taking the whole request down with it
        # (design.md, "Granica biegnie po tym, czyj to jest problem").
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
            # Trimmed to exactly `[start, end)` even when the requested
            # resolution already *is* `FINE_RESOLUTION` (or finer, raw MINUTE)
            # and `rows` is sitting right there — `rows` may reach back past
            # `start` for a different entry's warmup in the same request,
            # which `time_profile`/`session_range`/`opening_range` must not
            # see: none of them warm up, each reads exactly the window the
            # operator asked for.
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
    series = _build_series(rows)
    times_all = [row.period_start for row in rows]
    session_close_before = _session_close_before(times_all, body.resolution, gaps)

    minute_series = _build_series(minute_rows) if minute_rows else None
    minute_times = [row.period_start for row in minute_rows] if minute_rows else None

    results = [
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


def _session_close_before(
    times: Sequence[datetime],
    resolution: Resolution,
    gaps: Sequence[tuple[datetime, datetime]],
) -> np.ndarray:
    """`out[i]` is true when the stretch between bar `i - 1` and bar `i` is
    wider than one nominal period *and* the archive has verified it, meaning
    the candle that would have filled it never existed because the market was
    shut (`coverage.Absence.MARKET_CLOSED`) — as opposed to a stretch nobody
    has verified yet, `uncovered_within`'s `gaps`, which might just as well be
    a hole ingest left behind. Only the first is a session boundary; task 4.3
    is the difference, and it is the reason this reads `gaps` rather than the
    elapsed time alone.
    """
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
    session_close_before: np.ndarray,
    minute_series: Series | None,
    minute_times: list[datetime] | None,
    requested_start: datetime,
    missing_series: dict[Resolution, str],
) -> IndicatorResultOut:
    needed = entry.warmup_bars(params)
    settled = available_warmup_bars >= needed

    # Asked for before anything is computed: an entry whose series is not there has no
    # answer to give, and the reason belongs where its answer would have been.
    # `warmup_bars` stays null — nothing was read to warm anything up.
    #
    # Both series are checked, not whichever one the entry mostly uses. No entry wants
    # both today, and an `if/else` here would read as if that were guaranteed — the
    # first one that does would have its missing coarse series ignored, compute against
    # an empty `htf_periods` and answer with an empty `levels`: "computed, found none",
    # which is the exact claim this whole change exists to stop being made.
    wanted = (
        FINE_RESOLUTION if entry.needs_minute_series else None,
        entry.higher_resolution,
    )
    for resolution in wanted:
        if resolution is not None and resolution in missing_series:
            return IndicatorResultOut(
                id=entry.id, params=params, settled=False, error=missing_series[resolution]
            )

    # One case per computer, and the computer is what says which. This used to be a
    # chain of `if entry.compute_x is not None`, where the *order* of the branches was
    # the tie-break for an entry that had set two of them — a state nothing refused and
    # nobody meant. A `match` on the tagged union has no order to get wrong, and pyright
    # tells us when a case is missing rather than the entry silently falling through to
    # `lines` and answering with an empty dict.
    #
    # The two `warmup_bars` values are the real difference between these cases and not
    # an inconsistency: an entry reading its own series has a warmup measured in bars of
    # that series, and one reading a different series (a closed DAY candle, the fine
    # minute series) has none to measure — it is settled the moment its source is there.
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
