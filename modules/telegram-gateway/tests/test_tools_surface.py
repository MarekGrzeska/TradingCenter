"""What the tool surface announces, and the line that makes this set different from every other one
in the system: a tool here does something outside this system, and two acts are still kept off it."""

from __future__ import annotations

import json

import builders
import pytest
from fakes import FakeBotApi

from telegram_gateway.bot_api import Delivered

EXPECTED_TOOLS = {"telegram_destinations", "send_telegram_message"}

# Characters of the serialized `list_tools()`, read by a client before every turn — and this is the
# fifth such surface in the system. Measured 2 443 on 31 August 2026 for two tools; headroom ~20%.
SURFACE_CEILING_CHARS = 3_000

pytestmark = pytest.mark.db


async def call(tool_server, name: str, **arguments):
    """A tool called the way a client calls it, with the structured half of the answer. A tool
    answering with a list has it under `result`; one answering with an object is the object."""
    _, structured = await tool_server.call_tool(name, arguments)
    return structured["result"] if set(structured) == {"result"} else structured


async def _ready_destination(conn, name: str = "operator"):
    bot = await builders.bot(conn)
    destination = await builders.destination(conn, name=name, bot_id=bot.id)
    await conn.execute(
        "UPDATE destinations SET chat_id = 9, state = 'ready', bound_at = now() WHERE id = $1",
        destination.id,
    )
    return destination


async def test_the_expected_tools_and_no_others(tool_server) -> None:
    tools = await tool_server.list_tools()

    assert {tool.name for tool in tools} == EXPECTED_TOOLS


async def test_the_surface_holds_no_way_to_create_a_bot_or_bind_a_destination(
    tool_server,
) -> None:
    """The boundary this set exists to draw. A bot created and a destination bound outlive the
    conversation that asked for them, so they belong to the operator and to REST."""
    tools = await tool_server.list_tools()
    names = {tool.name for tool in tools}
    surface = json.dumps([tool.model_dump() for tool in tools]).lower()

    for act in ("create", "delete", "remove", "bind", "adopt"):
        assert not any(act in name for name in names), f"{act} is on the tool surface: {names}"
    # Nor by another name: a tool that handed out a start link would bind a destination without
    # being called one, and one that handed out a token would be worse.
    assert "start_link" not in surface
    assert "token" not in surface


async def test_only_sending_is_announced_as_changing_anything(tool_server) -> None:
    """The annotation is a structural claim a client may act on, so it has to be exact: reading who
    can be written to changes nothing, and sending is not idempotent — twice is two notifications."""
    by_name = {tool.name: tool.annotations for tool in await tool_server.list_tools()}

    assert by_name["telegram_destinations"].readOnlyHint is True
    assert by_name["send_telegram_message"].readOnlyHint is False
    assert by_name["send_telegram_message"].idempotentHint is False


async def test_the_surface_stays_within_what_a_conversation_pays_for_it(tool_server) -> None:
    tools = await tool_server.list_tools()
    payload = json.dumps([tool.model_dump() for tool in tools], ensure_ascii=False)

    assert len(payload) <= SURFACE_CEILING_CHARS, (
        f"the tool surface is {len(payload)} characters, over the {SURFACE_CEILING_CHARS} ceiling"
    )


async def test_a_model_can_learn_the_names_without_being_told_them(tool_server, db) -> None:
    await _ready_destination(db, "operator-primary")
    await builders.destination(db, name="waiting")

    listed = await call(tool_server, "telegram_destinations")

    by_name = {one["name"]: one for one in listed}
    assert by_name["operator-primary"]["receives"] is True
    assert by_name["waiting"]["receives"] is False
    assert by_name["waiting"]["state"] == "pending"


async def test_sending_answers_with_the_identifier_telegram_gave_it(
    tool_server, app, db
) -> None:
    await _ready_destination(db)
    app.state.telegram = FakeBotApi(send=Delivered(message_id=31, chat_id=9))

    sent = await call(tool_server, "send_telegram_message", destination="operator", text="hi")

    assert sent == {"destination": "operator", "message_id": 31}


async def test_an_empty_gateway_is_answered_rather_than_failed(tool_server) -> None:
    """A model that gets an error with no text says the notification was sent, or that the system
    is broken. Both are untrue, and only one of them is even a failure."""
    answer = await call(tool_server, "send_telegram_message", destination="operator", text="hi")

    assert "no destination bound" in answer["refused"]
    assert "operator binds" in answer["do_first"]


async def test_a_mistyped_name_is_told_apart_from_an_empty_gateway(tool_server, db) -> None:
    await _ready_destination(db, "operator-primary")

    answer = await call(tool_server, "send_telegram_message", destination="operatr", text="hi")

    assert "operatr" in answer["refused"]
    assert "telegram_destinations" in answer["do_first"]
