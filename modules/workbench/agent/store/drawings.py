"""Levels, zones and trend lines left on an instrument — objects, not a log."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

import asyncpg
from tc_runtime.db import Conn, fetch_one

from ..models import (
    ChartDrawing,
    ChartDrawingGeometry,
    ChartLevel,
    ChartTrendline,
    ChartTrendlinePoint,
    ChartZone,
)

# A hundred objects on one instrument is already a chart nothing can be read on, so the
# ceiling sits where usefulness already ends rather than at some larger, arbitrary number.
MAX_DRAWINGS_PER_SYMBOL = 100

# The largest value `chart_drawings.id` can hold. Checked before a query rather than left to the driver:
# asyncpg raises on an out-of-range integer, which for a tool call is a turn that died, not a refusal.
MAX_DRAWING_ID = 2**63 - 1

# A state of the instrument, not a log: there is no cursor and no "since sequence" read here — a consumer
# reads every drawing for a symbol and replaces what it shows with all of it.

_SELECT_DRAWING_COLUMNS = (
    "id, symbol, session_id, kind, time_a, price_a, time_b, price_b, label, color, "
    "hidden, created_at, updated_at"
)

_SELECT_DRAWINGS_BY_SYMBOL = f"""
    SELECT {_SELECT_DRAWING_COLUMNS}
      FROM chart_drawings
     WHERE symbol = $1
     ORDER BY id
"""

_COUNT_DRAWINGS_BY_SYMBOL = "SELECT count(*) AS n FROM chart_drawings WHERE symbol = $1"

_INSERT_DRAWING = f"""
    INSERT INTO chart_drawings
        (session_id, symbol, kind, time_a, price_a, time_b, price_b, label, color)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
    RETURNING {_SELECT_DRAWING_COLUMNS}
"""

_SELECT_DRAWING = f"""
    SELECT {_SELECT_DRAWING_COLUMNS}
      FROM chart_drawings
     WHERE id = $1
       FOR UPDATE
"""

_DELETE_DRAWINGS = """
    DELETE FROM chart_drawings
     WHERE symbol = $1 AND id = ANY($2::bigint[])
    RETURNING id
"""

_DELETE_DRAWING = "DELETE FROM chart_drawings WHERE id = $1 RETURNING id"

_UPDATE_DRAWING = f"""
    UPDATE chart_drawings
       SET price_a = COALESCE($2, price_a),
           price_b = COALESCE($3, price_b),
           label = COALESCE($4, label),
           hidden = COALESCE($5, hidden),
           updated_at = now()
     WHERE id = $1
    RETURNING {_SELECT_DRAWING_COLUMNS}
"""

# Scoped to the symbol, so an id belonging to another instrument comes back as untouched rather than
# quietly acted on. Returns only the rows that moved, so the caller can name the ids it could not act on.
_SET_DRAWINGS_HIDDEN = """
    UPDATE chart_drawings
       SET hidden = $3, updated_at = now()
     WHERE symbol = $1 AND id = ANY($2::bigint[])
    RETURNING id
"""


def _geometry_to_columns(
    geometry: ChartDrawingGeometry,
) -> tuple[str, datetime | None, float, datetime | None, float | None]:
    """The domain shape, flattened to the four columns the database actually has — the mirror of
    `_geometry_from_row` below. `kind` says which fields the other three mean."""
    if isinstance(geometry, ChartLevel):
        return "level", geometry.at, geometry.price, None, None
    if isinstance(geometry, ChartZone):
        return "zone", geometry.from_, geometry.bottom, geometry.to, geometry.top
    return "trendline", geometry.a.time, geometry.a.price, geometry.b.time, geometry.b.price


def _geometry_from_row(row: asyncpg.Record) -> ChartDrawingGeometry:
    kind = row["kind"]
    if kind == "level":
        return ChartLevel(price=row["price_a"], at=row["time_a"])
    if kind == "zone":
        return ChartZone(top=row["price_b"], bottom=row["price_a"], from_=row["time_a"], to=row["time_b"])
    if kind == "trendline":
        return ChartTrendline(
            a=ChartTrendlinePoint(time=row["time_a"], price=row["price_a"]),
            b=ChartTrendlinePoint(time=row["time_b"], price=row["price_b"]),
        )
    raise ValueError(f"unknown drawing kind in storage: {kind!r}")


def _drawing_from_row(row: asyncpg.Record) -> ChartDrawing:
    return ChartDrawing(
        id=row["id"],
        symbol=row["symbol"],
        session_id=row["session_id"],
        geometry=_geometry_from_row(row).model_copy(update={"label": row["label"], "color": row["color"]}),
        hidden=row["hidden"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def count_drawings(conn: Conn, *, symbol: str) -> int:
    row = await fetch_one(conn, _COUNT_DRAWINGS_BY_SYMBOL, symbol)
    return row["n"]


async def list_drawings(conn: Conn, *, symbol: str) -> list[ChartDrawing]:
    """Every drawing on `symbol`, oldest first. Unbounded, deliberately: this table's own ceiling already
    keeps one symbol's rows small, and a second limit would hide a violation of the first."""
    rows = await conn.fetch(_SELECT_DRAWINGS_BY_SYMBOL, symbol)
    return [_drawing_from_row(row) for row in rows]


async def add_drawings(
    conn: Conn,
    *,
    session_id: int | None,
    symbol: str,
    geometries: Sequence[ChartDrawingGeometry],
) -> list[ChartDrawing]:
    """Inserted one at a time rather than in bulk: `add` lists are short, and a loop of plain `INSERT ...
    RETURNING` needs no array-binding gymnastics. The ceiling is the caller's, inside the same transaction."""
    written: list[ChartDrawing] = []
    for geometry in geometries:
        kind, time_a, price_a, time_b, price_b = _geometry_to_columns(geometry)
        row = await fetch_one(
            conn,
            _INSERT_DRAWING,
            session_id,
            symbol,
            kind,
            time_a,
            price_a,
            time_b,
            price_b,
            geometry.label,
            geometry.color,
        )
        written.append(_drawing_from_row(row))
    return written


async def remove_drawings(conn: Conn, *, symbol: str, ids: Sequence[int]) -> list[int]:
    """The ids actually removed — scoped to `symbol`, so one belonging to a different instrument comes back
    as not removed, the same as one that never existed."""
    rows = await conn.fetch(_DELETE_DRAWINGS, symbol, list(ids))
    return [row["id"] for row in rows]


async def lock_drawing(conn: Conn, *, drawing_id: int) -> ChartDrawing | None:
    """One drawing, held until the surrounding transaction ends. `FOR UPDATE` because the only caller reads
    it to decide what a partial correction means, and that reading must not change under it."""
    row = await conn.fetchrow(_SELECT_DRAWING, drawing_id)
    return None if row is None else _drawing_from_row(row)


async def delete_drawing(conn: Conn, *, drawing_id: int) -> bool:
    """Whether a row was there to delete — the operator's own removal, which knows the id but not the
    symbol. `False` becomes a 404: a delete that quietly succeeded on nothing reads like one that worked."""
    return await conn.fetchval(_DELETE_DRAWING, drawing_id) is not None


async def update_drawing(
    conn: Conn,
    *,
    drawing_id: int,
    price_a: float | None,
    price_b: float | None,
    label: str | None,
    hidden: bool | None = None,
) -> ChartDrawing | None:
    """`None` on any field leaves it as it is — the same convention `PatchSessionIn` uses. `conn.fetchrow`,
    not `fetch_one`: an id nobody has is an expected outcome here, not a broken invariant."""
    row = await conn.fetchrow(_UPDATE_DRAWING, drawing_id, price_a, price_b, label, hidden)
    return None if row is None else _drawing_from_row(row)


async def set_drawings_hidden(
    conn: Conn, *, symbol: str, ids: Sequence[int], hidden: bool
) -> list[int]:
    """The ids actually switched — same contract as `remove_drawings`. Hiding is not removing: the drawing
    keeps its id, its moment and its geometry, so showing it again gives back exactly what was there."""
    rows = await conn.fetch(_SET_DRAWINGS_HIDDEN, symbol, list(ids), hidden)
    return [row["id"] for row in rows]
