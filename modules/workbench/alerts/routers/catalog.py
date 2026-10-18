"""What a rule can be made of, in one read. The form is built from this, so there is no field in it whose value the
operator has to remember."""

from __future__ import annotations

from fastapi import APIRouter, Request

from .. import known
from ..catalog import json_type, number_fields, usable
from ..contract import CatalogOut, DestinationOut, EventTypeOut, Problem, ToolOut
from ..gateway import GatewayUnreachable
from ..store import json_of, list_event_types, seen_values
from . import deps

router = APIRouter(tags=["catalogue"])


@router.get("/catalog", response_model=CatalogOut, responses={503: {"model": Problem}})
async def catalog(request: Request) -> CatalogOut:
    state = request.app.state
    tools = [tool for tool in await known.tools_of(state.tools) if usable(tool)]
    try:
        recipients = await known.recipients_of(state.gateway)
    except GatewayUnreachable as err:
        raise deps.refusal(503, str(err)) from err
    async with deps.connection(state.pool) as conn:
        types = await list_event_types(conn)
        seen = {row["name"]: await _seen(conn, row["name"], json_of(row["schema"])) for row in types}
    return CatalogOut(
        tools=[
            ToolOut(
                name=tool.name,
                description=tool.description,
                source=tool.source,
                arguments=tool.input_schema,
                number_fields=number_fields(tool.output_schema),
            )
            for tool in tools
        ],
        event_types=[
            EventTypeOut(
                name=row["name"],
                description=row["description"],
                schema=json_of(row["schema"]),
                announced_by=row["announced_by"],
                last_announced_at=row["last_announced_at"],
                seen=seen[row["name"]],
            )
            for row in types
        ],
        destinations=[
            DestinationOut(name=one.name, bot=bound.bot, receives=bound.receives)
            for one in recipients or []
            for bound in one.bindings
        ],
        gateway=recipients is not None,
        min_interval_seconds=state.settings.min_interval_seconds,
        drafting=state.drafter is not None,
        symbols=await known.symbols(state),
    )


async def _seen(conn, event_type: str, schema: dict) -> dict[str, list[str]]:
    """Values for the text attributes whose type asked to be offered by what it has had."""
    defs = {**schema.get("$defs", {}), **schema.get("definitions", {})}
    found: dict[str, list[str]] = {}
    for attribute, prop in schema.get("properties", {}).items():
        if prop.get("x-seen-values") is True and json_type(prop, defs) == "string":
            values = await seen_values(conn, event_type, attribute)
            if values:
                found[attribute] = values
    return found
