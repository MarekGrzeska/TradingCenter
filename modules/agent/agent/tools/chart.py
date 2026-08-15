"""The one tool this module owns rather than borrows.

Every other tool the model sees is announced by `market-mcp` and executed there
(`client.py`). This one is written here, in this module, and writes a row in this
module's database — it is the whole of the agent's write access, and its boundary is
named in `specs/agent-tools`, "Agent zapisuje wyłącznie w widoku terminala".

It never touches the terminal. It records what the operator's chart should show; the
terminal reads that log and applies it, which is what keeps the terminal the owner of
what it draws (design.md, "Polecenie jest deklaratywne i numerowane").

Checking happens **here**, before the row exists, because a refusal has to reach the
model — the only party that can correct it — inside the same turn (specs/agent-tools,
"Odmowa narzędzia jest wynikiem, nie awarią tury"). The catalogue and the tracked pairs
are read through `market-mcp`, the road this module already has; without that server
there is nothing to check against and the tool refuses rather than writing blind.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime
from typing import Any

import asyncpg

from .. import store
from ..models import ChartFocus, ChartIndicator, ChartSnapshot
from .client import ToolDescriptor, ToolOutcome, ToolOutcomeKind, ToolServer

CHART_TOOL_NAME = "set_chart"

# The candle count a focus may name, either around a point or as "the newest N". Below
# the floor a chart shows an approximation nobody could read; above the ceiling the
# terminal would need more history reads than a single pan should cost
# (design.md, "Granice liczby świec: 10 … 1000").
MIN_FOCUS_BARS = 10
MAX_FOCUS_BARS = 1000

# What the terminal offers as a palette; a colour outside it is not a colour it can draw
# (`terminal/src/chart/theme.ts`, `INDICATOR_LINE_TOKENS`). Duplicated rather than shared
# — there is no library between modules — and small enough that the duplication is
# visible when it drifts.
CHART_COLORS = (
    "--color-accent",
    "--color-indicator-2",
    "--color-up",
    "--color-indicator-4",
    "--color-indicator-5",
    "--color-indicator-6",
    "--color-indicator-7",
    "--color-down",
)

CHART_TOOL = ToolDescriptor(
    name=CHART_TOOL_NAME,
    description=(
        "Set what the operator's chart shows: its indicators, its symbol, its interval, "
        "and its focus — the span of time visible on it. Every field is optional and an "
        "omitted one is left as it is, so sending only `resolution` changes only the "
        "interval. `indicators` is the complete set to draw, not an addition: send every "
        "indicator that should be visible, and an empty list to draw none. `focus` moves "
        "the operator to a place on the chart; use it when they ask to be shown a "
        "particular moment or to zoom in or out, together with the other fields in one "
        "call if they ask for more than one at once. Use the rest of this tool when the "
        "operator asks to see something, or when what you found is easier to look at "
        "than to describe. Check the catalogue with list_indicators first if you are "
        "unsure of an id or a parameter range."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "instrument to show, e.g. US100; must be one market-data collects",
            },
            "resolution": {
                "type": "string",
                "description": "interval to show, e.g. MINUTE_5, HOUR, DAY; must be one this symbol is collected in",
            },
            "indicators": {
                "type": "array",
                "description": "the complete set of indicators to draw; [] draws none",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "catalogue id, e.g. ema"},
                        "params": {
                            "type": "object",
                            "description": "parameters by name; omitted ones take the catalogue default",
                            "additionalProperties": {"type": "number"},
                        },
                        "color": {
                            "type": "string",
                            "description": "one of " + ", ".join(CHART_COLORS) + "; omit to let the chart choose",
                            "enum": list(CHART_COLORS),
                        },
                    },
                    "required": ["id"],
                    "additionalProperties": False,
                },
            },
            "focus": {
                "type": "object",
                "description": (
                    "the span of time to show, given in exactly one of three shapes: "
                    "`from`+`to` (a range), `around`+`bars` (a point in time and a "
                    "number of candles around it), or `last_bars` alone (the newest N "
                    "candles). `from`, `to` and `around` are absolute ISO 8601 "
                    "timestamps with a UTC offset (e.g. '2026-01-03T09:00:00Z'), not "
                    "relative to now — `last_bars` is the one exception, and always "
                    f"means the end of the series. `bars` and `last_bars` must be "
                    f"between {MIN_FOCUS_BARS} and {MAX_FOCUS_BARS}."
                ),
                "properties": {
                    "from": {"type": "string", "description": "range start, ISO 8601 UTC"},
                    "to": {"type": "string", "description": "range end, ISO 8601 UTC"},
                    "around": {"type": "string", "description": "point in time, ISO 8601 UTC"},
                    "bars": {
                        "type": "integer",
                        "description": f"candles around `around`; {MIN_FOCUS_BARS}-{MAX_FOCUS_BARS}",
                    },
                    "last_bars": {
                        "type": "integer",
                        "description": f"newest N candles; {MIN_FOCUS_BARS}-{MAX_FOCUS_BARS}",
                    },
                },
                "additionalProperties": False,
            },
        },
        "additionalProperties": False,
    },
)


class ChartRefusal(Exception):
    """Something the model can fix by calling again — a sentence for it, not a stack
    trace for a log."""


def _as_indicators(raw: Any) -> list[ChartIndicator] | None:
    if raw is None:
        return None
    if not isinstance(raw, list):
        raise ChartRefusal("`indicators` must be a list; send [] to draw none.")
    indicators: list[ChartIndicator] = []
    for item in raw:
        if not isinstance(item, dict) or "id" not in item:
            raise ChartRefusal("every entry of `indicators` needs an `id` from the catalogue.")
        params = item.get("params") or {}
        if not isinstance(params, dict):
            raise ChartRefusal(f"`params` for {item['id']!r} must be an object of numbers.")
        try:
            indicators.append(
                ChartIndicator(
                    id=str(item["id"]),
                    params={name: float(value) for name, value in params.items()},
                    color=item.get("color"),
                )
            )
        except (TypeError, ValueError) as err:
            raise ChartRefusal(f"`params` for {item['id']!r} must be numbers: {err}") from err
    return indicators


def _parse_focus_time(raw: dict[str, Any], field: str) -> datetime:
    value = raw.get(field)
    if not isinstance(value, str):
        raise ChartRefusal(f"`focus.{field}` must be an ISO 8601 timestamp string.")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as err:
        raise ChartRefusal(
            f"`focus.{field}` is not a valid ISO 8601 timestamp: {value!r}."
        ) from err
    if parsed.tzinfo is None:
        raise ChartRefusal(
            f"`focus.{field}` must carry a UTC offset, e.g. '2026-01-03T09:00:00Z'."
        )
    return parsed


def _parse_focus_bars(raw: dict[str, Any], field: str) -> int:
    value = raw.get(field)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ChartRefusal(f"`focus.{field}` must be a whole number of candles.")
    if not (MIN_FOCUS_BARS <= value <= MAX_FOCUS_BARS):
        raise ChartRefusal(
            f"`focus.{field}`={value} must be between {MIN_FOCUS_BARS} and "
            f"{MAX_FOCUS_BARS} candles."
        )
    return value


def _as_focus(raw: Any, *, now: datetime) -> ChartFocus | None:
    """The chart's requested frame, or `None` to leave the operator looking where they
    are. Checked without reading anything: form, ordering, candle-count bounds, and
    whether the frame is entirely in the future — everything a consumer needs to know is
    already in the call (design.md, "Sprawdzenie kadru nie wymaga dodatkowego odczytu z
    archiwum")."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ChartRefusal("`focus` must be an object.")

    has_range = "from" in raw or "to" in raw
    has_point = "around" in raw or "bars" in raw
    has_last = "last_bars" in raw
    if sum((has_range, has_point, has_last)) != 1:
        raise ChartRefusal(
            "`focus` must be given exactly one way: a `from`/`to` range, an `around` "
            "point with `bars`, or `last_bars` alone — not zero of these and not more "
            "than one."
        )

    if has_last:
        last_bars = _parse_focus_bars(raw, "last_bars")
        return ChartFocus(last_bars=last_bars)

    if has_point:
        if "around" not in raw or "bars" not in raw:
            raise ChartRefusal("`focus.around` and `focus.bars` must be given together.")
        around = _parse_focus_time(raw, "around")
        bars = _parse_focus_bars(raw, "bars")
        if around > now:
            raise ChartRefusal(
                f"`focus.around` ({raw['around']}) is in the future; the archive has "
                "nothing there yet."
            )
        return ChartFocus(around=around, bars=bars)

    if "from" not in raw or "to" not in raw:
        raise ChartRefusal("`focus.from` and `focus.to` must be given together.")
    start = _parse_focus_time(raw, "from")
    end = _parse_focus_time(raw, "to")
    if start >= end:
        raise ChartRefusal(
            f"`focus.from` ({raw['from']}) must be earlier than `focus.to` ({raw['to']})."
        )
    if start > now:
        raise ChartRefusal(
            f"`focus.from` ({raw['from']}) is in the future; the archive has nothing "
            "there yet."
        )
    return ChartFocus(from_=start, to=end)


async def _read_json(tool_server: ToolServer, name: str, arguments: dict[str, Any]) -> Any:
    """One market-mcp call, answered as data rather than prose.

    A tool that refused or never answered is not something this tool can work around: it
    means the check cannot be made, and a command written without it would be a command
    the terminal then refuses to draw. Both come back as `ChartRefusal` — the model is
    told what is unknown rather than handed a chart that will not appear.
    """
    outcome = await tool_server.call(name, arguments)
    if outcome.kind is not ToolOutcomeKind.OK:
        raise ChartRefusal(
            f"cannot check this against the archive right now ({name}: {outcome.text}). "
            "Nothing was changed."
        )
    try:
        return json.loads(outcome.text)
    except json.JSONDecodeError as err:
        raise ChartRefusal(
            f"cannot check this against the archive right now ({name} answered "
            "something unreadable). Nothing was changed."
        ) from err


async def _check_pair(
    tool_server: ToolServer,
    symbol: str | None,
    resolution: str | None,
    chart: ChartSnapshot | None,
) -> None:
    if symbol is None and resolution is None:
        return
    pairs = await _read_json(tool_server, "list_tracked_pairs", {})
    if isinstance(pairs, dict):  # a structured-content envelope, if one ever arrives
        pairs = pairs.get("result", pairs.get("pairs", []))
    tracked: dict[str, set[str]] = {}
    for pair in pairs:
        tracked.setdefault(pair["symbol"], set()).add(pair["resolution"])

    if symbol is not None and symbol not in tracked:
        known = ", ".join(sorted(tracked)) or "none"
        raise ChartRefusal(
            f"{symbol!r} is not collected by the archive, so the chart would be empty. "
            f"Collected symbols: {known}."
        )
    # A symbol-only command still lands on whatever interval the chart already shows —
    # the terminal keeps its current one rather than picking a new one — so a symbol not
    # collected at it would draw nothing just the same as one refused outright. Checked
    # against the snapshot taken when the operator asked, not a later read of it
    # (`agent-chart-control`, "Kolor rozwiązywany przy rysowaniu z bieżących selekcji"
    # applies the same way here: what mattered is what was on screen at the time).
    effective_resolution = resolution if resolution is not None else (chart.resolution if chart else None)
    if effective_resolution is None:
        return
    # A resolution alone is checked against every collected pair: this tool does not know
    # which symbol the chart is on, and the terminal refuses the combination it cannot
    # draw anyway.
    allowed = tracked.get(symbol) if symbol is not None else set().union(*tracked.values()) if tracked else set()
    if effective_resolution not in (allowed or set()):
        where = f"for {symbol}" if symbol is not None else "for any collected symbol"
        known = ", ".join(sorted(allowed or set())) or "none"
        raise ChartRefusal(
            f"{effective_resolution!r} is not collected {where}. Collected there: {known}."
        )


async def _check_indicators(
    tool_server: ToolServer, indicators: list[ChartIndicator] | None
) -> None:
    if not indicators:
        return
    catalogue = await _read_json(tool_server, "list_indicators", {})
    if isinstance(catalogue, dict):  # a structured-content envelope, if one ever arrives
        catalogue = catalogue.get("indicators", catalogue.get("result", []))
    entries = {entry["id"]: entry for entry in catalogue}

    for indicator in indicators:
        entry = entries.get(indicator.id)
        if entry is None:
            raise ChartRefusal(
                f"{indicator.id!r} is not an indicator this archive computes. "
                "Call list_indicators to see the ids."
            )
        ranges = {param["name"]: param for param in entry.get("params", [])}
        for name, value in indicator.params.items():
            param = ranges.get(name)
            if param is None:
                known = ", ".join(sorted(ranges)) or "none"
                raise ChartRefusal(
                    f"{indicator.id!r} has no parameter {name!r}. Its parameters: {known}."
                )
            if not param["min"] <= value <= param["max"]:
                raise ChartRefusal(
                    f"{name}={value} is outside {indicator.id!r}'s range "
                    f"[{param['min']}, {param['max']}]."
                )
        if indicator.color is not None and indicator.color not in CHART_COLORS:
            raise ChartRefusal(
                f"{indicator.color!r} is not a colour the chart draws. "
                f"Use one of: {', '.join(CHART_COLORS)}."
            )


def _focus_text(focus: ChartFocus) -> str:
    if focus.last_bars is not None:
        return f"the newest {focus.last_bars} candles"
    if focus.around is not None and focus.bars is not None:
        return f"{focus.bars} candles around {focus.around.isoformat()}"
    if focus.from_ is not None and focus.to is not None:
        return f"{focus.from_.isoformat()} to {focus.to.isoformat()}"
    raise AssertionError(f"a focus must carry one recognised shape: {focus!r}")


def _confirmation(
    symbol: str | None,
    resolution: str | None,
    indicators: list[ChartIndicator] | None,
    focus: ChartFocus | None,
) -> str:
    parts: list[str] = []
    if symbol is not None:
        parts.append(f"symbol {symbol}")
    if resolution is not None:
        parts.append(f"interval {resolution}")
    if indicators is not None:
        drawn = ", ".join(
            indicator.id + (f"({_params_text(indicator)})" if indicator.params else "")
            for indicator in indicators
        )
        parts.append(f"indicators {drawn}" if drawn else "no indicators")
    if focus is not None:
        parts.append(f"focus {_focus_text(focus)}")
    return "the operator's chart is now set to " + "; ".join(parts) + "."


def _params_text(indicator: ChartIndicator) -> str:
    return ", ".join(
        f"{name}={value:g}" for name, value in sorted(indicator.params.items())
    )


class ChartTool:
    """The tool as the turn sees it: a descriptor to announce and one call to run.

    Holds the pool rather than a connection — a turn's tool call happens long after the
    request that started it released its own.
    """

    name = CHART_TOOL_NAME
    descriptor = CHART_TOOL

    def __init__(self, pool: asyncpg.Pool, tool_server: ToolServer | None) -> None:
        self._pool = pool
        self._tool_server = tool_server

    async def call(
        self,
        arguments: dict[str, Any],
        *,
        session_id: int,
        chart: ChartSnapshot | None = None,
    ) -> ToolOutcome:
        started = time.monotonic()

        def elapsed() -> int:
            return int((time.monotonic() - started) * 1000)

        def refuse(sentence: str) -> ToolOutcome:
            return ToolOutcome(ToolOutcomeKind.REFUSED, sentence, elapsed())

        symbol = arguments.get("symbol")
        resolution = arguments.get("resolution")
        try:
            indicators = _as_indicators(arguments.get("indicators"))
        except ChartRefusal as err:
            return refuse(str(err))
        try:
            focus = _as_focus(arguments.get("focus"), now=datetime.now(UTC))
        except ChartRefusal as err:
            return refuse(str(err))

        if symbol is None and resolution is None and indicators is None and focus is None:
            return refuse(
                "nothing to set: send at least one of `symbol`, `resolution`, "
                "`indicators`, `focus`."
            )

        # Only symbol, resolution and indicators need the archive to check — a focus is
        # checked entirely above, without a read (design.md, "Sprawdzenie kadru nie
        # wymaga dodatkowego odczytu z archiwum"). A call naming only a focus must not
        # refuse for a reason that has nothing to do with what it is setting.
        needs_archive = symbol is not None or resolution is not None or indicators is not None

        if needs_archive and (self._tool_server is None or not self._tool_server.configured):
            # Supported configuration (`MARKET_MCP_URL` unset), and the honest answer is
            # that the check cannot be made — not a command written blind.
            return refuse(
                "no archive to check this against right now, so the chart was left alone."
            )

        if needs_archive:
            # Independent reads, run together: neither check uses the other's answer, and
            # sequencing them only adds one round trip's latency to every call that names
            # both a pair and indicators. `return_exceptions=True` because `gather`
            # otherwise abandons whichever task didn't raise first, which asyncio logs as
            # an exception that was never retrieved — both are checked in the order they
            # were checked before, so a refusal from the pair still wins the same way it
            # did sequentially.
            assert self._tool_server is not None
            results = await asyncio.gather(
                _check_pair(self._tool_server, symbol, resolution, chart),
                _check_indicators(self._tool_server, indicators),
                return_exceptions=True,
            )
            for result in results:
                if isinstance(result, ChartRefusal):
                    return refuse(str(result))
                if isinstance(result, BaseException):
                    raise result

        # Written whole or not at all: three indicators of which one is unknown is a
        # refusal, never two drawn (specs/agent-chart-control, "Odmowa nie zostawia
        # śladu na wykresie").
        async with self._pool.acquire() as conn:
            await store.record_chart_command(
                conn,
                session_id=session_id,
                symbol=symbol,
                resolution=resolution,
                indicators=indicators,
                focus=focus,
            )
        return ToolOutcome(
            ToolOutcomeKind.OK,
            _confirmation(symbol, resolution, indicators, focus),
            elapsed(),
        )
