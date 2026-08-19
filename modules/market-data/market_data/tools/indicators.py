"""The indicator catalogue, and computing entries from it — reduced to what changed
recently rather than the full series a chart would draw
(`market-data-tools`, "Zestaw odpowiada na pytania o wskaźniki").
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from ..contract import IndicatorSpecIn as IndicatorSpecWire
from ..contract import IndicatorsRequest
from ..indicators import service
from ..reads import read_series
from . import reduce, uncertainty
from ._shared import (
    PERIOD_SECONDS,
    READ_ONLY,
    ToolContext,
    WindowedOut,
    is_tracked,
    resolution_of,
    resolve_window,
)
from .errors import ToolRefusal

INDICATOR_HARD_LIMIT = 10
SERIES_POINT_LIMIT = 200
NEAR_PRICE_LIMIT = 20

LATEST_LOOKBACK_BARS = 50
SLOPE_LOOKBACK_BARS = 10

# `levels_near_price` surveys structural indicators (swing points, session ranges,
# htf pivots) whose meaningful recent state does not fit in a handful of bars the way
# a moving average's does — a starting point, like every other ceiling here
# (design.md, "Sufity są liczbami w kodzie... do zmierzenia po E2").
LEVELS_LOOKBACK = timedelta(days=30)

# --- output shapes ---


class IndicatorParamOut(BaseModel):
    name: str
    type: str
    default: float
    min: float
    max: float


class IndicatorSummaryOut(BaseModel):
    id: str
    name: str
    group: str
    output: str
    aliases: list[str] = Field(default_factory=list)
    params: list[IndicatorParamOut] = Field(default_factory=list)


class ListIndicatorsOut(BaseModel):
    algorithm_version: int
    group: str | None = None
    indicators: list[IndicatorSummaryOut]


class IndicatorLineSpecOut(BaseModel):
    key: str
    label: str
    style: str | None = None


class IndicatorRenderOut(BaseModel):
    pane: str
    style: str
    scale: str = "price"
    autoscale: bool = True
    levels: list[float] = Field(default_factory=list)


class IndicatorDetailOut(BaseModel):
    id: str
    name: str
    aliases: list[str]
    group: str
    output: str
    params: list[IndicatorParamOut]
    lines: list[IndicatorLineSpecOut]
    render: IndicatorRenderOut
    warmup_kind: str


class IndicatorSpecIn(BaseModel):
    id: str = Field(examples=["ema"])
    params: dict[str, float] = Field(default_factory=dict)


class LineLatestOut(BaseModel):
    key: str
    label: str
    value: float | None = Field(
        default=None, description="null when the line never settles in this window"
    )
    slope_per_bar: float | None = Field(
        default=None, description="change per bar over the trailing lookback"
    )
    distance_from_price: float | None = Field(
        default=None, description="last close minus this line's last value"
    )
    distance_from_price_percent: float | None = None
    bars_since_price_crossed: int | None = Field(
        default=None, description="null when no crossing was found within the window read"
    )


class LineSeriesOut(BaseModel):
    key: str
    label: str
    values: list[float | None]


class IndicatorMarkerOut(BaseModel):
    time: datetime
    label: str
    price: float | None = None


class IndicatorZoneOut(BaseModel):
    # The two aliases rather than `alias="from"`, for `WindowedOut`'s reason: with one
    # alias pyright synthesizes an `__init__` taking a parameter literally named `from`,
    # which is a keyword and so unwritable, and rejects every construction here. These
    # used to be built by `model_validate` off a dict, where that never came up; they are
    # built by name now that the shapes arrive as models rather than as JSON.
    from_: datetime = Field(validation_alias="from", serialization_alias="from")
    to: datetime | None = None
    top: float
    bottom: float
    direction: str | None = None
    touched_at: datetime | None = None
    filled_at: datetime | None = None

    model_config = {"populate_by_name": True}


class IndicatorLevelOut(BaseModel):
    from_: datetime = Field(validation_alias="from", serialization_alias="from")
    price: float
    label: str | None = None
    count: int | None = None

    model_config = {"populate_by_name": True}


class ComputedIndicatorOut(BaseModel):
    id: str
    output: str
    settled: bool
    error: str | None = None
    notes: list[str] = Field(default_factory=list, description="e.g. why settled is false")

    # lines, mode="latest"
    latest: list[LineLatestOut] | None = None
    # lines, mode="series"
    times: list[datetime] | None = None
    series: list[LineSeriesOut] | None = None
    series_thinned: bool = False
    series_original_point_count: int | None = None

    # markers / zones / levels — mode does not apply
    markers: list[IndicatorMarkerOut] | None = None
    zones: list[IndicatorZoneOut] | None = None
    levels: list[IndicatorLevelOut] | None = None
    omitted: int = 0


class ComputeIndicatorsOut(WindowedOut):
    symbol: str
    resolution: str
    mode: str
    results: list[ComputedIndicatorOut]
    notes: list[str] = Field(default_factory=list)


class NearPriceItemOut(BaseModel):
    indicator_id: str
    kind: str = Field(description="level, zone, or marker")
    time: datetime
    price: float
    label: str | None = None
    distance: float = Field(description="reference_price - price")
    distance_percent: float | None = None


class LevelsNearPriceOut(BaseModel):
    symbol: str
    resolution: str
    group: str | None = None
    reference_price: float
    reference_time: datetime
    items: list[NearPriceItemOut]
    omitted: int = Field(default=0, description="matches beyond the closest ones shown")
    notes: list[str] = Field(default_factory=list)


# --- the catalogue, read where it lives ---


class _Catalogue:
    """The catalogue as two lookups, built once at first use.

    It used to be fetched over HTTP and cached because the fetch cost a request. There is
    no request now — this is the same tuple the REST route serves — so what is left of the
    cache is the two dictionaries, worth building once rather than per call.
    """

    def __init__(self) -> None:
        self._entries: dict | None = None
        self._by_alias: dict[str, str] = {}
        self._algorithm_version: int = 0

    def _load(self) -> None:
        if self._entries is not None:
            return
        published = service.catalogue()
        self._algorithm_version = published.algorithm_version
        self._entries = {entry.id: entry for entry in published.indicators}
        self._by_alias = {
            alias: entry.id for entry in published.indicators for alias in entry.aliases
        }

    @property
    def algorithm_version(self) -> int:
        self._load()
        return self._algorithm_version

    @property
    def entries(self) -> dict:
        self._load()
        assert self._entries is not None
        return self._entries

    @property
    def by_alias(self) -> dict[str, str]:
        self._load()
        return self._by_alias


def _validate_spec_ids(spec_ids: list[str], cache: _Catalogue) -> None:
    """Refuses rather than substitutes — an alias hit is named, never silently used
    (specs/market-data-tools, "MUST NOT podstawić w jego miejsce wpisu podobnego z nazwy")."""
    for entry_id in spec_ids:
        if entry_id in cache.entries:
            continue
        if entry_id in cache.by_alias:
            raise ToolRefusal(
                f"no indicator named {entry_id!r}. Closest by alias: "
                f"{cache.by_alias[entry_id]!r}. See list_indicators for the full catalogue."
            )
        raise ToolRefusal(
            f"no indicator named {entry_id!r}. See list_indicators for the full catalogue."
        )


def _param_out(param) -> IndicatorParamOut:
    return IndicatorParamOut(
        name=param.name, type=param.type, default=param.default, min=param.min, max=param.max
    )


def _summary_out(entry) -> IndicatorSummaryOut:
    return IndicatorSummaryOut(
        id=entry.id,
        name=entry.name,
        group=entry.group,
        output=entry.output,
        aliases=list(entry.aliases),
        params=[_param_out(p) for p in entry.params],
    )


def _detail_out(entry) -> IndicatorDetailOut:
    return IndicatorDetailOut(
        id=entry.id,
        name=entry.name,
        aliases=list(entry.aliases),
        group=entry.group,
        output=entry.output,
        params=[_param_out(p) for p in entry.params],
        lines=[
            IndicatorLineSpecOut(key=line.key, label=line.label, style=line.style)
            for line in entry.lines
        ],
        render=IndicatorRenderOut(
            pane=entry.render.pane,
            style=entry.render.style,
            scale=entry.render.scale,
            autoscale=entry.render.autoscale,
            levels=list(entry.render.levels),
        ),
        warmup_kind=entry.warmup_kind,
    )


# --- "latest" mode: a line's current reading against price ---


def _latest_window(to_iso: str | None, resolution: str) -> tuple[datetime, datetime]:
    end = datetime.fromisoformat(to_iso) if to_iso else datetime.now(UTC)
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    seconds = PERIOD_SECONDS.get(resolution, PERIOD_SECONDS["MINUTE"])
    start = end - timedelta(seconds=seconds * LATEST_LOOKBACK_BARS)
    return start, end


async def _closes_by_time(
    ctx: ToolContext, symbol: str, resolution: str, start: datetime, end: datetime
) -> dict[datetime, float]:
    async with ctx.pool.acquire() as conn:
        series = await read_series(conn, symbol, resolution_of(resolution), start, end)
    return {c.period_start: c.close for c in series.candles if c.close is not None}


def _last_non_none_index(values: list[float | None]) -> int | None:
    for i in range(len(values) - 1, -1, -1):
        if values[i] is not None:
            return i
    return None


def _sign(close: float | None, value: float | None) -> int | None:
    if close is None or value is None:
        return None
    diff = close - value
    return 0 if diff == 0 else (1 if diff > 0 else -1)


def _bars_since_cross(
    values: list[float | None], times: list[datetime], closes: dict[datetime, float], last_idx: int
) -> int | None:
    current = _sign(closes.get(times[last_idx]), values[last_idx])
    if current is None:
        return None
    for offset in range(1, last_idx + 1):
        i = last_idx - offset
        sign = _sign(closes.get(times[i]), values[i])
        if sign is None:
            continue
        if sign != current and sign != 0:
            return offset - 1
    return None


def _line_latest(
    key: str,
    label: str,
    values: list[float | None],
    times: list[datetime],
    closes: dict[datetime, float],
) -> LineLatestOut:
    last_idx = _last_non_none_index(values)
    if last_idx is None:
        return LineLatestOut(key=key, label=label)

    # `_last_non_none_index` guarantees this is not None; the checker cannot see that.
    last_value = values[last_idx]
    assert last_value is not None

    lookback_idx = max(0, last_idx - SLOPE_LOOKBACK_BARS)
    lookback_value = values[lookback_idx]
    slope = None
    if lookback_idx != last_idx and lookback_value is not None:
        slope = (last_value - lookback_value) / (last_idx - lookback_idx)

    last_close = closes.get(times[last_idx])
    distance = distance_pct = None
    if last_close is not None:
        distance = last_close - last_value
        if last_value:
            distance_pct = distance / last_value * 100

    return LineLatestOut(
        key=key,
        label=label,
        value=last_value,
        slope_per_bar=slope,
        distance_from_price=distance,
        distance_from_price_percent=distance_pct,
        bars_since_price_crossed=_bars_since_cross(values, times, closes, last_idx),
    )


def _reduce_result(
    raw,
    entry,
    times: list[datetime],
    mode: str,
    closes: dict[datetime, float],
) -> ComputedIndicatorOut:
    output = entry.output if entry is not None else "unknown"
    notes = (
        [uncertainty.unsettled_sentence(raw.warmup_bars)]
        if not raw.settled and not raw.error
        else []
    )
    base = {
        "id": raw.id,
        "output": output,
        "settled": raw.settled,
        "error": raw.error,
        "notes": notes,
    }
    if raw.error:
        return ComputedIndicatorOut(**base)

    line_labels = {line.key: line.label for line in entry.lines} if entry is not None else {}

    if output == "lines":
        lines = raw.lines or {}
        if mode == "latest":
            latest = [
                _line_latest(key, line_labels.get(key, key), values, times, closes)
                for key, values in lines.items()
            ]
            return ComputedIndicatorOut(**base, latest=latest)

        thinned_times, stride = reduce.thin_series(times, SERIES_POINT_LIMIT)
        series = [
            LineSeriesOut(
                key=key,
                label=line_labels.get(key, key),
                values=reduce.thin_series(values, SERIES_POINT_LIMIT)[0],
            )
            for key, values in lines.items()
        ]
        return ComputedIndicatorOut(
            **base,
            times=thinned_times,
            series=series,
            series_thinned=stride is not None,
            series_original_point_count=len(times) if stride is not None else None,
        )

    if output == "markers":
        ordered = sorted(raw.markers or [], key=lambda m: m.time, reverse=True)
        kept, dropped = reduce.truncate(ordered, NEAR_PRICE_LIMIT)
        return ComputedIndicatorOut(
            **base,
            markers=[IndicatorMarkerOut(time=m.time, label=m.label, price=m.price) for m in kept],
            omitted=dropped,
        )

    if output == "zones":
        ordered = sorted(raw.zones or [], key=lambda z: z.touched_at or z.from_, reverse=True)
        kept, dropped = reduce.truncate(ordered, NEAR_PRICE_LIMIT)
        return ComputedIndicatorOut(
            **base,
            zones=[
                IndicatorZoneOut(
                    from_=z.from_,
                    to=z.to,
                    top=z.top,
                    bottom=z.bottom,
                    direction=z.direction,
                    touched_at=z.touched_at,
                    filled_at=z.filled_at,
                )
                for z in kept
            ],
            omitted=dropped,
        )

    if output == "levels":
        ordered = sorted(raw.levels or [], key=lambda lv: lv.from_, reverse=True)
        kept, dropped = reduce.truncate(ordered, NEAR_PRICE_LIMIT)
        return ComputedIndicatorOut(
            **base,
            levels=[
                IndicatorLevelOut(from_=lv.from_, price=lv.price, label=lv.label, count=lv.count)
                for lv in kept
            ],
            omitted=dropped,
        )

    return ComputedIndicatorOut(**base)


# --- levels_near_price ---


def _chunks(items: list, size: int) -> Iterator[list]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _near_price_item(
    indicator_id: str,
    kind: str,
    moment: datetime,
    price: float,
    label: str | None,
    reference_price: float,
) -> NearPriceItemOut:
    distance = reference_price - price
    distance_percent = distance / reference_price * 100 if reference_price else None
    return NearPriceItemOut(
        indicator_id=indicator_id,
        kind=kind,
        time=moment,
        price=price,
        label=label,
        distance=distance,
        distance_percent=distance_percent,
    )


async def _compute(
    ctx: ToolContext,
    symbol: str,
    resolution: str,
    start: datetime,
    end: datetime,
    specs: list[tuple[str, dict[str, float]]],
):
    """One computation, through the same service and the same ceiling the REST route uses.

    `ctx.indicator_limiter` is that route's own semaphore, not a second one: two entrances
    to one computation with one ceiling between them (design.md, D1).
    """
    request = IndicatorsRequest(
        resolution=resolution_of(resolution),
        from_=start,
        to=end,
        specs=[IndicatorSpecWire(id=entry_id, params=params) for entry_id, params in specs],
    )
    try:
        return await service.compute(symbol, request, ctx.pool, ctx.indicator_limiter)
    except service.IndicatorRequestRejected as rejected:
        raise ToolRefusal(str(rejected)) from rejected


def register(mcp: FastMCP, ctx: ToolContext) -> None:
    catalogue = _Catalogue()

    @mcp.tool(annotations=READ_ONLY)
    async def list_indicators(group: str | None = None) -> ListIndicatorsOut:
        """Every indicator this archive can compute, its parameters and their
        defaults — enough to build a request without knowing any indicator by name
        beforehand. Narrow to one group (e.g. "averages", "oscillators", "structure")
        to keep the reply short; omit it for the whole catalogue.
        """
        entries = list(catalogue.entries.values())
        if group is not None:
            entries = [e for e in entries if e.group == group]
        return ListIndicatorsOut(
            algorithm_version=catalogue.algorithm_version,
            group=group,
            indicators=[_summary_out(e) for e in entries],
        )

    @mcp.tool(annotations=READ_ONLY)
    async def describe_indicator(id: str) -> IndicatorDetailOut:
        """The full catalogue entry for one indicator: parameter ranges, aliases,
        output shape and how it likes to be drawn. Read this before calling
        compute_indicators with a parameter you are not sure is in range.
        """
        _validate_spec_ids([id], catalogue)
        return _detail_out(catalogue.entries[id])

    @mcp.tool(annotations=READ_ONLY)
    async def compute_indicators(
        symbol: str,
        specs: list[IndicatorSpecIn],
        resolution: str = "MINUTE",
        mode: str = "latest",
        from_iso: str | None = None,
        to_iso: str | None = None,
    ) -> ComputeIndicatorsOut:
        """Compute one or more named indicators on one shared time axis. Most questions
        need 1-3; above 10 in one call it refuses. `from_iso`/`to_iso` (mode="series"
        only) are UTC, ISO-8601. Distances are measured against the last **bid** close.

        mode="latest" (default): each line's current value, its slope over the trailing
        bars, its distance from the last close and how many bars since it last crossed
        price. mode="series": the window's full series, thinned to at most 200 points per
        line. Indicators whose output is not `lines` (markers/zones/levels) ignore `mode`
        and come back as the freshest 20 entries either way.
        """
        if len(specs) > INDICATOR_HARD_LIMIT:
            raise ToolRefusal(
                f"{len(specs)} indicators requested, above the {INDICATOR_HARD_LIMIT}-"
                "indicator ceiling for one call. Split the request."
            )
        if mode not in ("latest", "series"):
            raise ToolRefusal(f"mode must be 'latest' or 'series', got {mode!r}.")

        _validate_spec_ids([s.id for s in specs], catalogue)

        start, end = (
            resolve_window(from_iso, to_iso)
            if mode == "series"
            else _latest_window(to_iso, resolution)
        )

        computed = await _compute(
            ctx, symbol, resolution, start, end, [(s.id, s.params) for s in specs]
        )
        times = list(computed.times)

        notes: list[str] = []
        uncovered_note = uncertainty.uncovered_sentence(
            [(u.from_, u.to) for u in computed.uncovered]
        )
        if uncovered_note:
            notes.append(uncovered_note)
        derived_note = uncertainty.derived_sentence(computed.derived, resolution)
        if derived_note:
            notes.append(derived_note)

        needs_closes = mode == "latest" and any(
            not raw.error and getattr(catalogue.entries.get(raw.id), "output", None) == "lines"
            for raw in computed.results
        )
        closes = await _closes_by_time(ctx, symbol, resolution, start, end) if needs_closes else {}

        results = [
            _reduce_result(raw, catalogue.entries.get(raw.id), times, mode, closes)
            for raw in computed.results
        ]

        return ComputeIndicatorsOut(
            symbol=symbol,
            resolution=resolution,
            from_=start,
            to=end,
            mode=mode,
            results=results,
            notes=notes,
        )

    @mcp.tool(annotations=READ_ONLY)
    async def levels_near_price(
        symbol: str, resolution: str = "MINUTE", group: str | None = None
    ) -> LevelsNearPriceOut:
        """Every level, zone and marker the catalogue can compute for this pair over
        the last 30 days, merged into one list sorted by distance from the last
        **bid** close (UTC) — the closest 20, further ones counted in `omitted`.
        Narrow to one group to avoid surveying the whole catalogue; omit it to check
        everything.
        """
        candidates = [
            e
            for e in catalogue.entries.values()
            if e.output in ("levels", "zones", "markers")
            and (group is None or e.group == group)
        ]
        if not candidates:
            raise ToolRefusal(
                f"no levels/zones/markers indicators in group {group!r}. See list_indicators."
                if group
                else "no levels/zones/markers indicators in the catalogue."
            )

        end = datetime.now(UTC)
        start = end - LEVELS_LOOKBACK

        async with ctx.pool.acquire() as conn:
            price_series = await read_series(conn, symbol, resolution_of(resolution), start, end)
        if not price_series.candles:
            tracked = await is_tracked(ctx, symbol, resolution)
            raise ToolRefusal(uncertainty.empty_series_sentence(symbol, tracked))
        last_candle = price_series.candles[-1]
        if last_candle.close is None:
            raise ToolRefusal(
                f"{symbol}'s last candle has no close price to measure distance from."
            )
        reference_price = last_candle.close
        reference_time = last_candle.period_start

        items: list[NearPriceItemOut] = []
        for chunk in _chunks(candidates, INDICATOR_HARD_LIMIT):
            computed = await _compute(
                ctx, symbol, resolution, start, end, [(e.id, {}) for e in chunk]
            )
            for raw in computed.results:
                if raw.error:
                    continue
                for lv in raw.levels or []:
                    items.append(
                        _near_price_item(
                            raw.id, "level", lv.from_, lv.price, lv.label, reference_price
                        )
                    )
                for z in raw.zones or []:
                    midpoint = (z.top + z.bottom) / 2
                    items.append(
                        _near_price_item(
                            raw.id,
                            "zone",
                            z.touched_at or z.from_,
                            midpoint,
                            z.direction,
                            reference_price,
                        )
                    )
                for m in raw.markers or []:
                    if m.price is None:
                        continue
                    items.append(
                        _near_price_item(
                            raw.id, "marker", m.time, m.price, m.label, reference_price
                        )
                    )

        items.sort(key=lambda item: abs(item.distance))
        kept, dropped = reduce.truncate(items, NEAR_PRICE_LIMIT)

        return LevelsNearPriceOut(
            symbol=symbol,
            resolution=resolution,
            group=group,
            reference_price=reference_price,
            reference_time=reference_time,
            items=kept,
            omitted=dropped,
        )
