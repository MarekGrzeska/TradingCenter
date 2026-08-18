"""The indicator catalogue, and computing entries from it — reduced to what changed
recently rather than the full series a chart would draw
(`market-mcp-tools`, "Zestaw odpowiada na pytania o wskaźniki").
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from .. import reduce, uncertainty
from ..client import UpstreamClient
from ..errors import ToolRefusal
from ..upstream import UpstreamCandles
from ._shared import (
    PERIOD_SECONDS,
    READ_ONLY,
    WindowedOut,
    is_tracked,
    raise_for_status,
    resolve_window,
)

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
    from_: datetime = Field(alias="from")
    to: datetime | None = None
    top: float
    bottom: float
    direction: str | None = None
    touched_at: datetime | None = None
    filled_at: datetime | None = None

    model_config = {"populate_by_name": True}


class IndicatorLevelOut(BaseModel):
    from_: datetime = Field(alias="from")
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


# --- catalogue cache (task 3.1) ---


class _CatalogueCache:
    def __init__(self) -> None:
        self.algorithm_version: int | None = None
        self.entries: dict[str, dict] = {}
        self.by_alias: dict[str, str] = {}

    @property
    def is_loaded(self) -> bool:
        return self.algorithm_version is not None

    def store(self, algorithm_version: int, raw_entries: list[dict]) -> None:
        self.algorithm_version = algorithm_version
        self.entries = {e["id"]: e for e in raw_entries}
        self.by_alias = {alias: e["id"] for e in raw_entries for alias in e.get("aliases", [])}


async def _ensure_catalogue(upstream: UpstreamClient, cache: _CatalogueCache) -> _CatalogueCache:
    """Fetched once per process and kept. The catalogue changes on a market-data
    deployment — which restarts this module's own process too, far more often than an
    operator would ever notice one stale entry."""
    if cache.is_loaded:
        return cache
    response = await upstream.get("/indicators")
    await raise_for_status(response)
    body = response.json()
    cache.store(body["algorithm_version"], body["indicators"])
    return cache


def _validate_spec_ids(spec_ids: list[str], cache: _CatalogueCache) -> None:
    """Refuses rather than substitutes — an alias hit is named, never silently used
    (specs/market-mcp-tools, "MUST NOT podstawić w jego miejsce wpisu podobnego z nazwy")."""
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


def _param_out(p: dict) -> IndicatorParamOut:
    return IndicatorParamOut(
        name=p["name"], type=p["type"], default=p["default"], min=p["min"], max=p["max"]
    )


def _summary_out(entry: dict) -> IndicatorSummaryOut:
    return IndicatorSummaryOut(
        id=entry["id"],
        name=entry["name"],
        group=entry["group"],
        output=entry["output"],
        aliases=entry.get("aliases", []),
        params=[_param_out(p) for p in entry["params"]],
    )


def _detail_out(entry: dict) -> IndicatorDetailOut:
    render = entry["render"]
    return IndicatorDetailOut(
        id=entry["id"],
        name=entry["name"],
        aliases=entry.get("aliases", []),
        group=entry["group"],
        output=entry["output"],
        params=[_param_out(p) for p in entry["params"]],
        lines=[
            IndicatorLineSpecOut(key=line["key"], label=line["label"], style=line.get("style"))
            for line in entry.get("lines", [])
        ],
        render=IndicatorRenderOut(
            pane=render["pane"],
            style=render["style"],
            scale=render.get("scale", "price"),
            autoscale=render.get("autoscale", True),
            levels=render.get("levels", []),
        ),
        warmup_kind=entry["warmup_kind"],
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
    upstream: UpstreamClient, symbol: str, resolution: str, start: datetime, end: datetime
) -> dict[datetime, float]:
    response = await upstream.get(
        f"/candles/{symbol}",
        params={"resolution": resolution, "from": start.isoformat(), "to": end.isoformat()},
    )
    await raise_for_status(response)
    parsed = UpstreamCandles.model_validate(response.json())
    return {c.time: c.close for c in parsed.candles if c.close is not None}


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
    raw: dict,
    entry: dict,
    times: list[datetime],
    mode: str,
    closes: dict[datetime, float],
) -> ComputedIndicatorOut:
    output = entry.get("output", "unknown") if entry else "unknown"
    settled = raw.get("settled", False)
    error = raw.get("error")
    notes = (
        [uncertainty.unsettled_sentence(raw.get("warmup_bars"))]
        if not settled and not error
        else []
    )
    base = {"id": raw["id"], "output": output, "settled": settled, "error": error, "notes": notes}
    if error:
        return ComputedIndicatorOut(**base)

    line_labels = {line["key"]: line["label"] for line in entry.get("lines", [])} if entry else {}

    if output == "lines":
        lines = raw.get("lines") or {}
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
        kept, dropped = reduce.cap_by_freshness(raw.get("markers") or [], "time", NEAR_PRICE_LIMIT)
        return ComputedIndicatorOut(
            **base, markers=[IndicatorMarkerOut.model_validate(m) for m in kept], omitted=dropped
        )

    if output == "zones":
        zones = raw.get("zones") or []
        ordered = sorted(zones, key=lambda z: z.get("touched_at") or z["from"], reverse=True)
        kept, dropped = reduce.truncate(ordered, NEAR_PRICE_LIMIT)
        return ComputedIndicatorOut(
            **base, zones=[IndicatorZoneOut.model_validate(z) for z in kept], omitted=dropped
        )

    if output == "levels":
        kept, dropped = reduce.cap_by_freshness(raw.get("levels") or [], "from", NEAR_PRICE_LIMIT)
        return ComputedIndicatorOut(
            **base, levels=[IndicatorLevelOut.model_validate(lv) for lv in kept], omitted=dropped
        )

    return ComputedIndicatorOut(**base)


# --- levels_near_price ---


def _chunks(items: list, size: int) -> Iterator[list]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _near_price_item(
    indicator_id: str,
    kind: str,
    time_iso: str,
    price: float,
    label: str | None,
    reference_price: float,
) -> NearPriceItemOut:
    distance = reference_price - price
    distance_percent = distance / reference_price * 100 if reference_price else None
    return NearPriceItemOut(
        indicator_id=indicator_id,
        kind=kind,
        time=datetime.fromisoformat(time_iso),
        price=price,
        label=label,
        distance=distance,
        distance_percent=distance_percent,
    )


def register(mcp: FastMCP, upstream: UpstreamClient) -> None:
    catalogue = _CatalogueCache()

    @mcp.tool(annotations=READ_ONLY)
    async def list_indicators(group: str | None = None) -> ListIndicatorsOut:
        """Every indicator this archive can compute, its parameters and their
        defaults — enough to build a request without knowing any indicator by name
        beforehand. Narrow to one group (e.g. "averages", "oscillators", "structure")
        to keep the reply short; omit it for the whole catalogue.
        """
        cache = await _ensure_catalogue(upstream, catalogue)
        assert cache.algorithm_version is not None  # _ensure_catalogue guarantees this
        entries = list(cache.entries.values())
        if group is not None:
            entries = [e for e in entries if e["group"] == group]
        return ListIndicatorsOut(
            algorithm_version=cache.algorithm_version,
            group=group,
            indicators=[_summary_out(e) for e in entries],
        )

    @mcp.tool(annotations=READ_ONLY)
    async def describe_indicator(id: str) -> IndicatorDetailOut:
        """The full catalogue entry for one indicator: parameter ranges, aliases,
        output shape and how it likes to be drawn. Read this before calling
        compute_indicators with a parameter you are not sure is in range.
        """
        cache = await _ensure_catalogue(upstream, catalogue)
        _validate_spec_ids([id], cache)
        return _detail_out(cache.entries[id])

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

        cache = await _ensure_catalogue(upstream, catalogue)
        _validate_spec_ids([s.id for s in specs], cache)

        start, end = (
            resolve_window(from_iso, to_iso)
            if mode == "series"
            else _latest_window(to_iso, resolution)
        )

        body = {
            "resolution": resolution,
            "from": start.isoformat(),
            "to": end.isoformat(),
            "specs": [{"id": s.id, "params": s.params} for s in specs],
        }
        response = await upstream.compute_indicators(symbol, body)
        await raise_for_status(response)
        payload = response.json()
        times = [datetime.fromisoformat(t) for t in payload["times"]]

        notes: list[str] = []
        uncovered_note = uncertainty.uncovered_sentence(
            [
                (datetime.fromisoformat(u["from"]), datetime.fromisoformat(u["to"]))
                for u in payload.get("uncovered", [])
            ]
        )
        if uncovered_note:
            notes.append(uncovered_note)
        derived_note = uncertainty.derived_sentence(payload["derived"], resolution)
        if derived_note:
            notes.append(derived_note)

        needs_closes = mode == "latest" and any(
            not r.get("error") and cache.entries.get(r["id"], {}).get("output") == "lines"
            for r in payload["results"]
        )
        closes = (
            await _closes_by_time(upstream, symbol, resolution, start, end) if needs_closes else {}
        )

        results = [
            _reduce_result(raw, cache.entries.get(raw["id"], {}), times, mode, closes)
            for raw in payload["results"]
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
        cache = await _ensure_catalogue(upstream, catalogue)
        candidates = [
            e
            for e in cache.entries.values()
            if e["output"] in ("levels", "zones", "markers")
            and (group is None or e["group"] == group)
        ]
        if not candidates:
            raise ToolRefusal(
                f"no levels/zones/markers indicators in group {group!r}. See list_indicators."
                if group
                else "no levels/zones/markers indicators in the catalogue."
            )

        end = datetime.now(UTC)
        start = end - LEVELS_LOOKBACK

        price_response = await upstream.get(
            f"/candles/{symbol}",
            params={"resolution": resolution, "from": start.isoformat(), "to": end.isoformat()},
        )
        await raise_for_status(price_response)
        price_parsed = UpstreamCandles.model_validate(price_response.json())
        if not price_parsed.candles:
            tracked = await is_tracked(upstream, symbol, resolution)
            raise ToolRefusal(uncertainty.empty_series_sentence(symbol, tracked))
        last_candle = price_parsed.candles[-1]
        if last_candle.close is None:
            raise ToolRefusal(
                f"{symbol}'s last candle has no close price to measure distance from."
            )
        reference_price = last_candle.close
        reference_time = last_candle.time

        items: list[NearPriceItemOut] = []
        for chunk in _chunks(candidates, INDICATOR_HARD_LIMIT):
            body = {
                "resolution": resolution,
                "from": start.isoformat(),
                "to": end.isoformat(),
                "specs": [{"id": e["id"], "params": {}} for e in chunk],
            }
            response = await upstream.compute_indicators(symbol, body)
            await raise_for_status(response)
            payload = response.json()
            for raw in payload["results"]:
                if raw.get("error"):
                    continue
                entry_id = raw["id"]
                for lv in raw.get("levels") or []:
                    items.append(
                        _near_price_item(
                            entry_id,
                            "level",
                            lv["from"],
                            lv["price"],
                            lv.get("label"),
                            reference_price,
                        )
                    )
                for z in raw.get("zones") or []:
                    midpoint = (z["top"] + z["bottom"]) / 2
                    items.append(
                        _near_price_item(
                            entry_id,
                            "zone",
                            z.get("touched_at") or z["from"],
                            midpoint,
                            z.get("direction"),
                            reference_price,
                        )
                    )
                for m in raw.get("markers") or []:
                    if m.get("price") is None:
                        continue
                    items.append(
                        _near_price_item(
                            entry_id,
                            "marker",
                            m["time"],
                            m["price"],
                            m.get("label"),
                            reference_price,
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
