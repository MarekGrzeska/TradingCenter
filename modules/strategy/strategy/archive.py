"""market-data as this module consumes it, and the only place that talks to it — the REST contract, not `/mcp`, which
is too tight for a loop reading three hundred bars. A read that fails is never an empty read."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from azure.core.exceptions import AzureError
from azure.identity.aio import DefaultAzureCredential

from .errors import ArchiveRefused, ArchiveUnreachable
from .periods import bars_between, period_length, window_for
from .spec import Candle, Fact, Facts, FactValue, Level, Marker, StrategySpec, Zone

log = logging.getLogger(__name__)

# Connect stays short: an archive that is not listening should be reported now, not after a minute.
# Read is generous because an indicator request over a long range is a computation, not a fetch.
DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=5.0)

# market-data refuses a request whose range exceeds this many bars, warmup included. Named here so the
# client can split a long read rather than let the archive refuse one.
REQUEST_CEILING_BARS = 200_000

# Held back from the ceiling so a fact's own warmup — which the archive reads *before* the
# requested range — cannot push a window that just fits into one that just does not.
CEILING_MARGIN_BARS = 1_000


class _ManagedIdentityAuth(httpx.Auth):
    """A bearer token on every request, from this module's own identity — per request, because one read
    at start-up expires. Unlike the gateway's twin there is no shared key to fall back to."""

    def __init__(self, credential: DefaultAzureCredential, scope: str) -> None:
        self._credential = credential
        self._scope = scope

    async def async_auth_flow(
        self, request: httpx.Request
    ) -> AsyncGenerator[httpx.Request, httpx.Response]:
        try:
            token = await self._credential.get_token(self._scope)
        except AzureError as err:
            log.warning("no token for %s; the archive will refuse this request: %s", self._scope, err)
        else:
            request.headers["Authorization"] = f"Bearer {token.token}"
        yield request


def http_client(
    scope: str | None = None, timeout: httpx.Timeout = DEFAULT_TIMEOUT
) -> httpx.AsyncClient:
    """A client for the archive, presenting this module's identity where it has one. Left out — local
    work, and every test — nothing is presented, which the archive supports."""
    auth = _ManagedIdentityAuth(DefaultAzureCredential(), scope) if scope else None
    return httpx.AsyncClient(timeout=timeout, auth=auth)


@dataclass(frozen=True)
class Gap:
    """A stretch of a requested range the archive never verified."""

    start: datetime
    end: datetime


@dataclass(frozen=True)
class AnnouncedParam:
    """One parameter of an archive indicator, with the range the archive publishes."""

    name: str
    type: str
    default: float
    min: float
    max: float


@dataclass(frozen=True)
class AnnouncedIndicator:
    """One catalogue entry of the archive, as much of it as this module has a use for. Its `params` and
    `lines` are what makes a configurator possible without inventing a second catalogue."""

    id: str
    name: str
    group: str
    output: str
    params: tuple[AnnouncedParam, ...] = ()
    lines: tuple[str, ...] = ()

    def param(self, name: str) -> AnnouncedParam | None:
        return next((param for param in self.params if param.name == name), None)


@dataclass(frozen=True)
class FactsRead:
    """Everything one evaluation needs, and what was missing from it."""

    facts: Facts
    gaps: tuple[Gap, ...] = ()


class Archive:
    """The archive's REST contract, as the four questions this module asks of it."""

    def __init__(self, base_url: str, client: httpx.AsyncClient) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client

    async def announced_indicators(self) -> frozenset[str]:
        """Every indicator id the archive's catalogue carries — what a strategy's facts are checked
        against, where the answer can be had rather than assumed at import."""
        body = await self._get("/indicators", params={}, what="the indicator catalogue")
        return frozenset(str(entry["id"]) for entry in body.get("indicators", []))

    async def announced_catalogue(self) -> dict[str, AnnouncedIndicator]:
        """The archive's indicator catalogue, keyed by id, kept whole rather than reduced to ids: a rule
        is checked against ranges and line keys. Nothing is cached — a stale copy is a second truth."""
        body = await self._get("/indicators", params={}, what="the indicator catalogue")
        return {entry.id: entry for entry in (_announced(row) for row in body.get("indicators", []))}

    async def last_closed_bar(self, symbol: str, resolution: str) -> datetime | None:
        """When the most recent closed bar of this pair opened, or `None`. `GET /candles` answers with
        closed bars only, which is why this module needs no rule about when a period ends."""
        period = period_length(resolution)
        # Three periods back: enough that a quiet market or a late write still yields a
        # bar, small enough that this stays a cheap query on every wake.
        now = datetime.now(tz=UTC)
        rows = await self._candles(symbol, resolution, now - period * 3, now + period)
        return rows[-1].time if rows else None

    async def read_facts(
        self,
        spec: StrategySpec,
        symbol: str,
        params: Mapping[str, float],
        *,
        as_of: datetime,
        bars_from: datetime | None = None,
    ) -> FactsRead:
        """Everything `evaluate` will be handed, for the bar that opened at `as_of` — one request per
        resolution rather than per fact. `bars_from` widens it, with each fact's warmup added before it."""
        gaps: list[Gap] = []
        start, end = window_for(spec.resolution, last_bar=as_of, bars=spec.candles)
        if bars_from is not None:
            start = min(start, bars_from - period_length(spec.resolution) * spec.candles)
        candles = await self._candles(symbol, spec.resolution, start, end)

        values: dict[str, FactValue] = {}
        for resolution, facts in _by_resolution(spec.facts).items():
            read, resolution_gaps = await self._indicators(
                symbol, resolution, facts, params, as_of=as_of, bars_from=bars_from
            )
            values.update(read)
            gaps.extend(resolution_gaps)

        return FactsRead(
            facts=Facts(symbol=symbol, as_of=as_of, candles=candles, values=values),
            gaps=tuple(gaps),
        )

    async def _candles(
        self, symbol: str, resolution: str, start: datetime, end: datetime
    ) -> tuple[Candle, ...]:
        rows: list[Candle] = []
        for window_start, window_end in _split(resolution, start, end):
            body = await self._get(
                f"/candles/{symbol}",
                params={
                    "resolution": resolution,
                    "from": _wire(window_start),
                    "to": _wire(window_end),
                },
                what=f"candles for {symbol} {resolution}",
            )
            rows.extend(
                Candle(
                    time=_instant(row["time"]),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                )
                for row in body.get("candles", [])
                # A candle whose OHLC is not all there cannot be reasoned about, and the
                # archive's own contract allows any of the four to be null.
                if all(row.get(field) is not None for field in ("open", "high", "low", "close"))
            )
        return tuple(rows)

    async def _indicators(
        self,
        symbol: str,
        resolution: str,
        facts: Sequence[Fact],
        params: Mapping[str, float],
        *,
        as_of: datetime,
        bars_from: datetime | None = None,
    ) -> tuple[dict[str, FactValue], list[Gap]]:
        bars = max(fact.bars for fact in facts)
        start, end = window_for(resolution, last_bar=as_of, bars=bars)
        if bars_from is not None:
            start = min(start, bars_from - period_length(resolution) * bars)
        body = await self._post(
            f"/indicators/{symbol}",
            json={
                "resolution": resolution,
                "from": _wire(start),
                "to": _wire(end),
                "specs": [
                    {"id": fact.indicator, "params": fact.resolved_params(params)}
                    for fact in facts
                ],
            },
            what=f"indicators for {symbol} {resolution}",
        )

        times = tuple(_instant(value) for value in body.get("times", []))
        results = body.get("results", [])
        if len(results) != len(facts):
            raise ArchiveRefused(
                f"asked the archive for {len(facts)} indicator(s) on {symbol} {resolution} "
                f"and got {len(results)} back"
            )

        values: dict[str, FactValue] = {}
        for fact, result in zip(facts, results, strict=True):
            # The archive answers in the order it was asked. Checked rather than trusted: this is a
            # contract across a module boundary, and a mismatch would rename one indicator's numbers.
            if result.get("id") != fact.indicator:
                raise ArchiveRefused(
                    f"the archive answered {result.get('id')!r} where "
                    f"{fact.indicator!r} was asked for"
                )
            values[fact.name] = _fact_value(fact, resolution, times, result)

        gaps = [
            Gap(start=_instant(gap["from"]), end=_instant(gap["to"]))
            for gap in body.get("uncovered", [])
        ]
        return values, gaps

    async def _get(self, path: str, *, params: dict[str, Any], what: str) -> Any:
        try:
            response = await self._client.get(f"{self._base_url}{path}", params=params)
        except httpx.RequestError as err:
            raise ArchiveUnreachable(f"the archive did not answer for {what}: {err}") from err
        return _body(response, what)

    async def _post(self, path: str, *, json: dict[str, Any], what: str) -> Any:
        try:
            response = await self._client.post(f"{self._base_url}{path}", json=json)
        except httpx.RequestError as err:
            raise ArchiveUnreachable(f"the archive did not answer for {what}: {err}") from err
        return _body(response, what)


def _body(response: httpx.Response, what: str) -> Any:
    if response.is_error:
        raise ArchiveRefused(f"the archive refused {what}: {_detail(response)}")
    try:
        return response.json()
    except ValueError as err:
        raise ArchiveRefused(f"the archive's answer for {what} was not JSON: {err}") from err


def _detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text.strip() or response.reason_phrase
    if isinstance(body, dict) and isinstance(body.get("detail"), str):
        return body["detail"]
    return str(body)


def _announced(row: Any) -> AnnouncedIndicator:
    return AnnouncedIndicator(
        id=str(row["id"]),
        name=str(row.get("name", row["id"])),
        group=str(row.get("group", "")),
        output=str(row.get("output", "lines")),
        params=tuple(
            AnnouncedParam(
                name=str(param["name"]),
                type=str(param.get("type", "float")),
                default=float(param["default"]),
                min=float(param["min"]),
                max=float(param["max"]),
            )
            for param in (row.get("params") or [])
        ),
        lines=tuple(str(line["key"]) for line in (row.get("lines") or [])),
    )


def _by_resolution(facts: Iterable[Fact]) -> dict[str, list[Fact]]:
    grouped: dict[str, list[Fact]] = {}
    for fact in facts:
        grouped.setdefault(fact.resolution, []).append(fact)
    return grouped


def _split(resolution: str, start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    """One range as however many the archive will accept. The loop never reaches this; the backtest does,
    and the point of putting it here is that neither the strategy nor the caller knows the ceiling exists."""
    allowed = REQUEST_CEILING_BARS - CEILING_MARGIN_BARS
    if bars_between(resolution, start, end) <= allowed:
        return [(start, end)]
    period = period_length(resolution)
    span = period * allowed
    windows: list[tuple[datetime, datetime]] = []
    cursor = start
    while cursor < end:
        windows.append((cursor, min(cursor + span, end)))
        cursor += span
    return windows


def _fact_value(fact: Fact, resolution: str, times: tuple[datetime, ...], result: Any) -> FactValue:
    if result.get("error"):
        # One fact the archive could not compute. Carried rather than raised: the other facts were
        # answered, and it is the strategy's business whether it can decide without this one.
        return FactValue(key=fact.name, resolution=resolution, error=str(result["error"]))

    lines = {
        name: tuple(None if value is None else float(value) for value in values)
        for name, values in (result.get("lines") or {}).items()
    }
    markers = tuple(
        Marker(
            time=_instant(row["time"]),
            label=str(row.get("label", "")),
            price=None if row.get("price") is None else float(row["price"]),
        )
        for row in (result.get("markers") or [])
    )
    zones = tuple(
        Zone(
            start=_instant(row["from"]),
            end=None if row.get("to") is None else _instant(row["to"]),
            top=float(row["top"]),
            bottom=float(row["bottom"]),
            direction=row.get("direction"),
            touched_at=None if row.get("touched_at") is None else _instant(row["touched_at"]),
            filled_at=None if row.get("filled_at") is None else _instant(row["filled_at"]),
        )
        for row in (result.get("zones") or [])
    )
    levels = tuple(
        _level(row) for row in (result.get("levels") or [])
    )
    return FactValue(
        key=fact.name,
        resolution=resolution,
        times=times,
        lines=lines,
        markers=markers,
        zones=zones,
        levels=levels,
    )


def _level(row: Any) -> Level:
    return Level(
        time=_instant(row["from"]),
        price=float(row["price"]),
        label=None if row.get("label") is None else str(row["label"]),
        count=None if row.get("count") is None else int(row["count"]),
    )


def _instant(value: Any) -> datetime:
    """One wire timestamp as an aware instant. A naive value would compare unequal to every aware one
    this module holds, so it is given the zone it already meant."""
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _wire(value: datetime) -> str:
    return value.isoformat()
