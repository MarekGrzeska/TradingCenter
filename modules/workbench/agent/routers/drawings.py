"""`/drawings` — the objects standing on an instrument's chart, and the operator's hand
on them.

Global to the module, not scoped to an owner, for the same reason `/chart` is: there is
one chart and one operator, and `current_principal` is asked only to refuse an
unauthenticated request.

Read, correct, remove — and no POST. The agent writes through `store` the way `ChartTool`
does, and the operator does not place drawings in this change; drawing with the mouse is
a different one (design.md, "Publikacja: odczyt, poprawka, usunięcie — bez POST"). An
endpoint nobody calls is still surface to keep working.

Unlike `/chart`, nothing here has a cursor: a drawing is the instrument's state, read
whole and replaced whole by whoever draws it (design.md, "Rysunek jest stanem, nie
logiem").
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from .. import store
from ..auth import current_principal
from ..contract import ChartDrawingOut, PatchDrawingIn
from ..models import ChartDrawing, ChartLevel, ChartTrendline, ChartZone

router = APIRouter()


@router.get("/drawings")
async def list_drawings(
    request: Request,
    symbol: str = Query(description="the instrument whose drawings to read, e.g. US100"),
    _: str = Depends(current_principal),
) -> list[ChartDrawingOut]:
    async with request.app.state.agent.pool.acquire() as conn:
        drawings = await store.list_drawings(conn, symbol=symbol)
    return [ChartDrawingOut.from_drawing(drawing) for drawing in drawings]


def _resolve_prices(drawing: ChartDrawing, patch: PatchDrawingIn) -> tuple[float | None, float | None]:
    """The patch's human-named prices, turned into the two columns storage keeps — and
    refused when they name a role this drawing's shape does not have.

    Checked against the drawing as it stands, not against the patch alone: a zone given
    only a new `top` still has to end up above the `bottom` it already had, which is the
    reason the caller holds the row locked while this runs.
    """
    geometry = drawing.geometry

    def reject(*fields: str) -> None:
        named = [field for field in fields if getattr(patch, field) is not None]
        if named:
            raise HTTPException(
                422,
                f"{', '.join(named)} is not something a {geometry.kind} has; "
                f"correct a {geometry.kind} with "
                + {
                    "level": "`price`",
                    "zone": "`top` and `bottom`",
                    "trendline": "`a_price` and `b_price`",
                }[geometry.kind],
            )

    if isinstance(geometry, ChartLevel):
        reject("top", "bottom", "a_price", "b_price")
        return patch.price, None

    if isinstance(geometry, ChartZone):
        reject("price", "a_price", "b_price")
        bottom = patch.bottom if patch.bottom is not None else geometry.bottom
        top = patch.top if patch.top is not None else geometry.top
        if top <= bottom:
            raise HTTPException(
                422,
                f"a zone's top ({top:g}) must stay above its bottom ({bottom:g}); "
                "send both if you mean to move the band past itself.",
            )
        return patch.bottom, patch.top

    assert isinstance(geometry, ChartTrendline)
    reject("price", "top", "bottom")
    return patch.a_price, patch.b_price


@router.patch("/drawings/{drawing_id}")
async def patch_drawing(
    request: Request,
    drawing_id: int,
    patch: PatchDrawingIn,
    _: str = Depends(current_principal),
) -> ChartDrawingOut:
    """The correction keeps the drawing's identity: same id, same kind, same instrument,
    so a model that read the id before the operator moved the level still points at the
    same object (specs/agent-chart-drawings, "Operator cofa rysunek ręką")."""
    async with request.app.state.agent.pool.acquire() as conn, conn.transaction():
        standing = await store.lock_drawing(conn, drawing_id=drawing_id)
        if standing is None:
            raise HTTPException(404, f"no drawing #{drawing_id}")
        price_a, price_b = _resolve_prices(standing, patch)
        corrected = await store.update_drawing(
            conn,
            drawing_id=drawing_id,
            price_a=price_a,
            price_b=price_b,
            label=patch.label,
            hidden=patch.hidden,
        )
    # The row is locked for the whole transaction, so it cannot have gone between the
    # read and the write — this is the type narrowing, not a race being handled.
    assert corrected is not None
    return ChartDrawingOut.from_drawing(corrected)


@router.delete("/drawings/{drawing_id}", status_code=204)
async def delete_drawing(
    request: Request,
    drawing_id: int,
    _: str = Depends(current_principal),
) -> None:
    async with request.app.state.agent.pool.acquire() as conn:
        removed = await store.delete_drawing(conn, drawing_id=drawing_id)
    if not removed:
        # Not a quiet success: an object the operator saw and cannot remove is a fact
        # they need, and a 204 over nothing hides it until the next read brings the
        # drawing back (specs/terminal-chart, "Usunięcie się nie powiodło").
        raise HTTPException(404, f"no drawing #{drawing_id}")
