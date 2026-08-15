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

import json
import time
from typing import Any

import asyncpg

from .. import store
from ..models import ChartIndicator
from .client import ToolDescriptor, ToolOutcome, ToolOutcomeKind, ToolServer

CHART_TOOL_NAME = "set_chart"

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
        "Set what the operator's chart shows: its indicators, its symbol, its interval. "
        "Every field is optional and an omitted one is left as it is, so sending only "
        "`resolution` changes only the interval. `indicators` is the complete set to "
        "draw, not an addition: send every indicator that should be visible, and an "
        "empty list to draw none. Use it when the operator asks to see something, or "
        "when what you found is easier to look at than to describe. Check the catalogue "
        "with list_indicators first if you are unsure of an id or a parameter range."
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
    tool_server: ToolServer, symbol: str | None, resolution: str | None
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
    if resolution is None:
        return
    # A resolution alone is checked against every collected pair: this tool does not know
    # which symbol the chart is on, and the terminal refuses the combination it cannot
    # draw anyway.
    allowed = tracked.get(symbol) if symbol is not None else set().union(*tracked.values()) if tracked else set()
    if resolution not in (allowed or set()):
        where = f"for {symbol}" if symbol is not None else "for any collected symbol"
        known = ", ".join(sorted(allowed or set())) or "none"
        raise ChartRefusal(
            f"{resolution!r} is not collected {where}. Collected there: {known}."
        )


async def _check_indicators(
    tool_server: ToolServer, indicators: list[ChartIndicator] | None
) -> None:
    if not indicators:
        return
    catalogue = await _read_json(tool_server, "list_indicators", {})
    entries = {entry["id"]: entry for entry in catalogue.get("indicators", [])}

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


def _confirmation(
    symbol: str | None, resolution: str | None, indicators: list[ChartIndicator] | None
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
        self, arguments: dict[str, Any], *, session_id: int
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

        if symbol is None and resolution is None and indicators is None:
            return refuse(
                "nothing to set: send at least one of `symbol`, `resolution`, `indicators`."
            )

        if self._tool_server is None or not self._tool_server.configured:
            # Supported configuration (`MARKET_MCP_URL` unset), and the honest answer is
            # that the check cannot be made — not a command written blind.
            return refuse(
                "no archive to check this against right now, so the chart was left alone."
            )

        try:
            await _check_pair(self._tool_server, symbol, resolution)
            await _check_indicators(self._tool_server, indicators)
        except ChartRefusal as err:
            return refuse(str(err))

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
            )
        return ToolOutcome(
            ToolOutcomeKind.OK, _confirmation(symbol, resolution, indicators), elapsed()
        )
