"""What exists right now, gathered from where it lives: the tool surface, the announced event types, and the door's
recipients. Read on every save and every catalogue — each of the three changes without this package being told."""

from __future__ import annotations

import json
import logging

from .catalog import CatalogTool, ToolSource
from .gateway import Gateway, GatewayUnreachable, Recipient
from .store import json_of
from .validation import Known

log = logging.getLogger(__name__)


async def tools_of(source: ToolSource | None) -> list[CatalogTool]:
    return [] if source is None else await source.tools()


async def event_schemas(conn) -> dict[str, dict]:
    rows = await conn.fetch("SELECT name, schema FROM event_types")
    return {row["name"]: json_of(row["schema"]) for row in rows}


async def recipients_of(gateway: Gateway | None) -> list[Recipient] | None:
    """`None` when nobody can be asked — no door in this process, or one that did not answer. The caller decides what that
    means: a save refuses on a door that failed, and lets a rule through where there is none."""
    if gateway is None:
        return None
    return await gateway.recipients()


async def known(state, conn) -> Known:
    """Everything a rule is checked against. A door that is there and does not answer is an error to the caller, not a
    reason to accept a recipient unchecked."""
    tools = {tool.name: tool for tool in await tools_of(state.tools)}
    recipients = await recipients_of(state.gateway)
    return Known(
        tools=tools,
        event_types=await event_schemas(conn),
        destinations=None if recipients is None else frozenset(one.name for one in recipients),
        min_interval_seconds=state.settings.min_interval_seconds,
    )


# The one tool read for the pairs the archive follows. Optional: a process without it offers no instrument list, and the
# form then takes the symbol as typed.
SYMBOLS_TOOL = "list_tracked_symbols"


async def symbols(state) -> list[str]:
    """The instruments the archive follows, or none where it cannot be asked."""
    if state.tools is None:
        return []
    if SYMBOLS_TOOL not in {tool.name for tool in await state.tools.tools()}:
        return []
    outcome = await state.tools.call(SYMBOLS_TOOL, {})
    return symbols_from(outcome.text) if outcome.kind == "ok" else []


def symbols_from(text: str) -> list[str]:
    """The symbols out of what `list_tracked_symbols` answered, or none if it answered in a way this cannot read."""
    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        return []
    rows = payload.get("result") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return []
    return [str(row["symbol"]) for row in rows if isinstance(row, dict) and "symbol" in row]


async def recipients_if_possible(state) -> frozenset[str] | None:
    """For the list, which must still draw when the door is down: the rules are shown, unchecked."""
    try:
        recipients = await recipients_of(state.gateway)
    except GatewayUnreachable as err:
        log.info("the list of rules is shown without checking recipients: %s", err)
        return None
    return None if recipients is None else frozenset(one.name for one in recipients)
