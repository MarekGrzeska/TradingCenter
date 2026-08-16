"""The two tools that put objects on the operator's chart and read them back.

The second and third tools this module owns rather than borrows — `chart.py` was the
first, and everything its docstring says about checking before writing, refusing in a
sentence the model can act on, and never touching the terminal holds here unchanged.

What is different, and it is the one place this module deliberately contradicts
`set_chart`, is that `draw_on_chart` is **incremental**: `add` adds, `remove` removes,
and a drawing left out of both stays exactly where it was. `set_chart` is declarative
because forgetting an indicator costs one line the operator restores with a click; a
declarative `draw_on_chart` would let one forgetful call wipe supports collected over
weeks (specs/agent-chart-drawings, "Agent stawia i kasuje rysunki narzędziem").

Reading is a separate tool from writing on purpose: a read is safe to repeat and a write
is not, and one tool whose description mixes the two gets called for a read by a model
that then writes (design.md, "Dwa narzędzia: jedno pisze, drugie czyta").
"""

from __future__ import annotations

import json
import math
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any

import asyncpg

from .. import store
from ..models import (
    ChartDrawing,
    ChartDrawingGeometry,
    ChartLevel,
    ChartTrendline,
    ChartTrendlinePoint,
    ChartZone,
)
from ..store import MAX_DRAWINGS_PER_SYMBOL
from .chart import CHART_COLORS, ChartRefusal, read_json
from .client import ToolDescriptor, ToolOutcome, ToolOutcomeKind, ToolServer

DRAW_TOOL_NAME = "draw_on_chart"
LIST_DRAWINGS_TOOL_NAME = "list_chart_drawings"

_COLOR_SCHEMA = {
    "type": "string",
    "description": "one of " + ", ".join(CHART_COLORS) + "; omit to let the chart choose",
    "enum": list(CHART_COLORS),
}
_LABEL_SCHEMA = {
    "type": "string",
    "description": "short caption drawn next to the object, e.g. 'weekly high'",
}

# Three shapes, discriminated by `kind`, each with its own field names. A model handed
# `price_a`/`price_b` confuses them; one handed `top`/`bottom` cannot (design.md, "Zapis:
# cztery kolumny geometrii i CHECK per kształt" — the four columns are storage's
# business, and this is the other side of that translation).
_LEVEL_SCHEMA = {
    "type": "object",
    "description": "a single price: a support, a resistance, a level worth watching",
    "properties": {
        "kind": {"const": "level"},
        "price": {"type": "number", "description": "the price the level sits at"},
        "at": {
            "type": "string",
            "description": "optional moment the level starts from, ISO 8601 with a UTC "
            "offset; omit for a level that has always been there",
        },
        "label": _LABEL_SCHEMA,
        "color": _COLOR_SCHEMA,
    },
    "required": ["kind", "price"],
    "additionalProperties": False,
}
_ZONE_SCHEMA = {
    "type": "object",
    "description": "a band between two prices: supply, demand, an imbalance",
    "properties": {
        "kind": {"const": "zone"},
        "top": {"type": "number", "description": "upper price; must be above `bottom`"},
        "bottom": {"type": "number", "description": "lower price"},
        "from": {
            "type": "string",
            "description": "optional start of the band in time, ISO 8601 with a UTC offset",
        },
        "to": {
            "type": "string",
            "description": "optional end of the band in time, ISO 8601 with a UTC offset",
        },
        "label": _LABEL_SCHEMA,
        "color": _COLOR_SCHEMA,
    },
    "required": ["kind", "top", "bottom"],
    "additionalProperties": False,
}
_POINT_SCHEMA = {
    "type": "object",
    "properties": {
        "time": {"type": "string", "description": "ISO 8601 with a UTC offset"},
        "price": {"type": "number"},
    },
    "required": ["time", "price"],
    "additionalProperties": False,
}
_TRENDLINE_SCHEMA = {
    "type": "object",
    "description": "a line between two points, each a moment and a price",
    "properties": {
        "kind": {"const": "trendline"},
        "a": {**_POINT_SCHEMA, "description": "the earlier point"},
        "b": {**_POINT_SCHEMA, "description": "the later point; its time must be after a's"},
        "label": _LABEL_SCHEMA,
        "color": _COLOR_SCHEMA,
    },
    "required": ["kind", "a", "b"],
    "additionalProperties": False,
}

DRAW_TOOL = ToolDescriptor(
    name=DRAW_TOOL_NAME,
    description=(
        "Draw objects on an instrument's chart and take existing ones off, in one call. "
        "Drawings belong to the instrument, not to the interval or to what is on screen: "
        "they stay visible on every chart of that symbol and survive the conversation. "
        "This tool is incremental, not declarative — unlike set_chart, `add` only adds "
        "and only an id named in `remove` goes away, so a drawing you do not mention "
        "stays where it is. Moving a level means removing the old id and adding the new "
        "one in the same call. Use it when the operator asks to mark, note or keep a "
        "price; call list_chart_drawings first when you need the ids of what is already "
        "there. A drawing is something the operator wanted kept — it is not the output "
        "of levels_near_price, which recomputes support and resistance from the archive "
        "on every call."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "instrument to draw on, e.g. US100; must be one market-data collects",
            },
            "add": {
                "type": "array",
                "description": "drawings to put on the chart; omit or [] to only remove",
                "items": {"oneOf": [_LEVEL_SCHEMA, _ZONE_SCHEMA, _TRENDLINE_SCHEMA]},
            },
            "remove": {
                "type": "array",
                "description": "ids of drawings to take off, as given by list_chart_drawings",
                "items": {"type": "integer"},
            },
        },
        "required": ["symbol"],
        "additionalProperties": False,
    },
)

LIST_DRAWINGS_TOOL = ToolDescriptor(
    name=LIST_DRAWINGS_TOOL_NAME,
    description=(
        "Read the objects drawn on an instrument's chart, with the ids draw_on_chart "
        "needs to remove them. Works for any symbol, including one no chart is showing "
        "right now, and reads this module's own record rather than the archive — so it "
        "answers even when the archive does not. It changes nothing: call it whenever "
        "the operator asks what is marked on an instrument, and before removing "
        "anything."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "instrument whose drawings to read, e.g. US100",
            }
        },
        "required": ["symbol"],
        "additionalProperties": False,
    },
)


def _as_symbol(arguments: dict[str, Any]) -> str:
    symbol = arguments.get("symbol")
    if not isinstance(symbol, str) or not symbol.strip():
        raise ChartRefusal("`symbol` is required: name the instrument to draw on.")
    return symbol.strip()


def _as_price(raw: Any, field: str) -> float:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ChartRefusal(f"`{field}` must be a number.")
    value = float(raw)
    if not math.isfinite(value):
        raise ChartRefusal(f"`{field}` must be a finite number.")
    if value <= 0:
        raise ChartRefusal(
            f"`{field}`={value:g} is not a price this instrument could trade at; "
            "a drawing needs a price above zero."
        )
    return value


def _as_time(raw: Any, field: str) -> datetime:
    if not isinstance(raw, str):
        raise ChartRefusal(f"`{field}` must be an ISO 8601 timestamp string.")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as err:
        raise ChartRefusal(f"`{field}` is not a valid ISO 8601 timestamp: {raw!r}.") from err
    if parsed.tzinfo is None:
        raise ChartRefusal(
            f"`{field}` must carry a UTC offset, e.g. '2026-01-03T09:00:00Z'."
        )
    return parsed


def _optional_time(item: dict[str, Any], key: str, field: str) -> datetime | None:
    return None if item.get(key) is None else _as_time(item[key], field)


def _as_text(raw: Any, field: str) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ChartRefusal(f"`{field}` must be text.")
    collapsed = " ".join(raw.split())
    return collapsed or None


def _as_color(raw: Any) -> str | None:
    if raw is None:
        return None
    if raw not in CHART_COLORS:
        raise ChartRefusal(
            f"{raw!r} is not a colour the chart draws. Use one of: {', '.join(CHART_COLORS)}."
        )
    return raw


def _as_point(raw: Any, field: str) -> ChartTrendlinePoint:
    if not isinstance(raw, dict):
        raise ChartRefusal(f"`{field}` must be an object with a `time` and a `price`.")
    return ChartTrendlinePoint(
        time=_as_time(raw.get("time"), f"{field}.time"),
        price=_as_price(raw.get("price"), f"{field}.price"),
    )


def _as_geometry(item: Any, index: int) -> ChartDrawingGeometry:
    """One entry of `add`, as the model wrote it. Every invariant the database also holds
    is checked here first — not because the `CHECK` would miss it, but because a refusal
    is only useful if it reaches the model as a sentence in the same turn, and a
    constraint violation reaches it as a failed turn (specs/agent-chart-drawings, "Odmowa
    rysowania nazywa, co poprawić")."""
    where = f"`add[{index}]`"
    if not isinstance(item, dict):
        raise ChartRefusal(f"{where} must be an object with a `kind`.")
    kind = item.get("kind")
    label = _as_text(item.get("label"), f"{where}.label")
    color = _as_color(item.get("color"))

    if kind == "level":
        return ChartLevel(
            price=_as_price(item.get("price"), f"{where}.price"),
            at=_optional_time(item, "at", f"{where}.at"),
            label=label,
            color=color,
        )
    if kind == "zone":
        top = _as_price(item.get("top"), f"{where}.top")
        bottom = _as_price(item.get("bottom"), f"{where}.bottom")
        if top <= bottom:
            raise ChartRefusal(
                f"{where} is not a zone: `top`={top:g} must be above `bottom`={bottom:g}. "
                "Swap them if you had them the other way round."
            )
        return ChartZone(
            top=top,
            bottom=bottom,
            from_=_optional_time(item, "from", f"{where}.from"),
            to=_optional_time(item, "to", f"{where}.to"),
            label=label,
            color=color,
        )
    if kind == "trendline":
        a = _as_point(item.get("a"), f"{where}.a")
        b = _as_point(item.get("b"), f"{where}.b")
        if a.time >= b.time:
            raise ChartRefusal(
                f"{where} is not a trend line: its points must be apart in time, and "
                f"`b.time` ({b.time.isoformat()}) is not after `a.time` "
                f"({a.time.isoformat()})."
            )
        return ChartTrendline(a=a, b=b, label=label, color=color)

    raise ChartRefusal(
        f"{where} has no recognised `kind`: use 'level' (a `price`), 'zone' (a `top` and "
        "a `bottom`) or 'trendline' (two points `a` and `b`)."
    )


def _as_additions(raw: Any) -> list[ChartDrawingGeometry]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ChartRefusal("`add` must be a list of drawings.")
    return [_as_geometry(item, index) for index, item in enumerate(raw)]


def _as_removals(raw: Any) -> list[int]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ChartRefusal("`remove` must be a list of drawing ids.")
    ids: list[int] = []
    for item in raw:
        if isinstance(item, bool) or not isinstance(item, int):
            raise ChartRefusal(
                f"`remove` takes ids as whole numbers; {item!r} is not one. "
                "Call list_chart_drawings for the ids."
            )
        ids.append(item)
    return ids


async def _check_symbol(tool_server: ToolServer, symbol: str) -> None:
    """The same road, the same sentence and the same refusal `set_chart` uses — a symbol
    the archive does not collect is a chart with no candles to draw on."""
    pairs = await read_json(tool_server, "list_tracked_pairs", {})
    if isinstance(pairs, dict):  # a structured-content envelope, if one ever arrives
        pairs = pairs.get("result", pairs.get("pairs", []))
    tracked = {pair["symbol"] for pair in pairs}
    if symbol not in tracked:
        known = ", ".join(sorted(tracked)) or "none"
        raise ChartRefusal(
            f"{symbol!r} is not collected by the archive, so there is no chart to draw "
            f"on. Collected symbols: {known}."
        )


def _geometry_text(geometry: ChartDrawingGeometry) -> str:
    if isinstance(geometry, ChartLevel):
        body = f"level at {geometry.price:g}"
    elif isinstance(geometry, ChartZone):
        body = f"zone {geometry.bottom:g}-{geometry.top:g}"
    else:
        body = f"trend line {geometry.a.price:g} to {geometry.b.price:g}"
    return body + (f" ({geometry.label})" if geometry.label else "")


def _confirmation(added: list[ChartDrawing], removed: list[int], symbol: str, total: int) -> str:
    parts: list[str] = []
    if added:
        drawn = ", ".join(f"#{d.id} {_geometry_text(d.geometry)}" for d in added)
        parts.append(f"drew {drawn}")
    if removed:
        parts.append("removed " + ", ".join(f"#{drawing_id}" for drawing_id in sorted(removed)))
    return (
        f"{'; '.join(parts)} on {symbol}. It now carries {total} "
        f"{'drawing' if total == 1 else 'drawings'}."
    )


def _drawing_as_json(drawing: ChartDrawing) -> dict[str, Any]:
    """The stored drawing in the same field names `add` takes, so an id read here can be
    handed straight back to `remove` and a shape read here can be redrawn without
    translation."""
    geometry = drawing.geometry
    body: dict[str, Any]
    if isinstance(geometry, ChartLevel):
        body = {"kind": "level", "price": geometry.price}
        if geometry.at is not None:
            body["at"] = geometry.at.isoformat()
    elif isinstance(geometry, ChartZone):
        body = {"kind": "zone", "top": geometry.top, "bottom": geometry.bottom}
        if geometry.from_ is not None:
            body["from"] = geometry.from_.isoformat()
        if geometry.to is not None:
            body["to"] = geometry.to.isoformat()
    else:
        body = {
            "kind": "trendline",
            "a": {"time": geometry.a.time.isoformat(), "price": geometry.a.price},
            "b": {"time": geometry.b.time.isoformat(), "price": geometry.b.price},
        }
    return {
        "id": drawing.id,
        **body,
        "label": geometry.label,
        "color": geometry.color,
        "created_at": drawing.created_at.isoformat(),
    }


def _clock() -> Callable[[], int]:
    """Milliseconds since this was called — every `ToolOutcome` carries one, and the two
    tools below measure it the same way `ChartTool` does."""
    started = time.monotonic()
    return lambda: int((time.monotonic() - started) * 1000)


class DrawOnChartTool:
    """`draw_on_chart` as the turn sees it. Holds the pool for the same reason `ChartTool`
    does: a tool call happens long after the request that started the turn let go of its
    connection."""

    name = DRAW_TOOL_NAME
    descriptor = DRAW_TOOL

    def __init__(self, pool: asyncpg.Pool, tool_server: ToolServer | None) -> None:
        self._pool = pool
        self._tool_server = tool_server

    async def call(self, arguments: dict[str, Any], *, session_id: int) -> ToolOutcome:
        elapsed = _clock()

        def refuse(sentence: str) -> ToolOutcome:
            return ToolOutcome(ToolOutcomeKind.REFUSED, sentence, elapsed())

        try:
            symbol = _as_symbol(arguments)
            additions = _as_additions(arguments.get("add"))
            removals = _as_removals(arguments.get("remove"))
        except ChartRefusal as err:
            return refuse(str(err))

        if not additions and not removals:
            return refuse(
                "nothing to do: send `add` with drawings to make, `remove` with ids to "
                "take off, or both."
            )

        if self._tool_server is None or not self._tool_server.configured:
            return refuse(
                "no archive to check the symbol against right now, so nothing was drawn."
            )
        try:
            await _check_symbol(self._tool_server, symbol)
        except ChartRefusal as err:
            return refuse(str(err))

        # One transaction around the whole call: three drawings of which one does not fit
        # under the ceiling means none of them is written, and a removal whose id turns
        # out not to exist takes its own deletion back with it (specs/agent-chart-
        # drawings, "Jedno wywołanie MUST zostać wykonane w całości albo wcale").
        #
        # Removals run first so that a call at the ceiling which swaps one drawing for
        # another — the shape "move this level" takes — fits where two separate calls
        # would have had to be ordered by hand.
        try:
            async with self._pool.acquire() as conn, conn.transaction():
                removed = (
                    await store.remove_drawings(conn, symbol=symbol, ids=removals)
                    if removals
                    else []
                )
                missing = sorted(set(removals) - set(removed))
                if missing:
                    raise ChartRefusal(
                        "no drawing on "
                        f"{symbol} with {'id' if len(missing) == 1 else 'ids'} "
                        + ", ".join(f"#{drawing_id}" for drawing_id in missing)
                        + " — it may have been removed by the operator in the meantime. "
                        "Call list_chart_drawings to see what is there now; nothing was "
                        "changed."
                    )
                standing = await store.count_drawings(conn, symbol=symbol)
                if standing + len(additions) > MAX_DRAWINGS_PER_SYMBOL:
                    raise ChartRefusal(
                        f"{symbol} already carries {standing} drawings and the limit is "
                        f"{MAX_DRAWINGS_PER_SYMBOL}, so these {len(additions)} would not "
                        "fit. Remove some first; nothing was drawn."
                    )
                added = (
                    await store.add_drawings(
                        conn, session_id=session_id, symbol=symbol, geometries=additions
                    )
                    if additions
                    else []
                )
                total = standing + len(added)
        except ChartRefusal as err:
            return refuse(str(err))

        return ToolOutcome(
            ToolOutcomeKind.OK, _confirmation(added, removed, symbol, total), elapsed()
        )


class ListChartDrawingsTool:
    """`list_chart_drawings`. No tool server: this reads this module's own table, which
    is why it still answers when the archive does not — and why it never checks the
    symbol, since a symbol with no drawings and a symbol the archive dropped both
    honestly answer "nothing drawn here"."""

    name = LIST_DRAWINGS_TOOL_NAME
    descriptor = LIST_DRAWINGS_TOOL

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def call(self, arguments: dict[str, Any]) -> ToolOutcome:
        elapsed = _clock()
        try:
            symbol = _as_symbol(arguments)
        except ChartRefusal as err:
            return ToolOutcome(ToolOutcomeKind.REFUSED, str(err), elapsed())

        async with self._pool.acquire() as conn:
            drawings = await store.list_drawings(conn, symbol=symbol)

        # JSON, like every market-mcp answer the model already reads: the ids have to
        # survive being read back into a `remove`, and prose is where ids get rounded,
        # reordered or dropped.
        payload = {
            "symbol": symbol,
            "drawings": [_drawing_as_json(drawing) for drawing in drawings],
        }
        return ToolOutcome(ToolOutcomeKind.OK, json.dumps(payload), elapsed())


__all__ = [
    "DRAW_TOOL",
    "DRAW_TOOL_NAME",
    "LIST_DRAWINGS_TOOL",
    "LIST_DRAWINGS_TOOL_NAME",
    "DrawOnChartTool",
    "ListChartDrawingsTool",
]
