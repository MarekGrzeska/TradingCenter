"""The group tools on the wire: a lookalike is a question for the model, not a second group. What counts as a
lookalike is `test_group_names.py`; what a merge does to the rows is `test_store.py`."""

from __future__ import annotations

import pytest

from . import fakes

pytestmark = pytest.mark.db


async def _call(tool_server, name: str, arguments: dict) -> dict:
    _content, structured = await tool_server.call_tool(name, arguments)
    # A tool returning `Model | dict` has its answer wrapped under "result" by FastMCP.
    return structured.get("result", structured)


async def test_a_lookalike_name_is_refused_until_the_model_confirms_it(tool_server) -> None:
    await _call(tool_server, "create_group", {"name": "Tariffs"})

    refused = await _call(tool_server, "create_group", {"name": "tariff"})
    confirmed = await _call(tool_server, "create_group", {"name": "tariff", "confirm_new": True})

    assert refused["similar_groups"] == ["Tariffs"]
    assert confirmed["already_existed"] is False
    groups = await _call(tool_server, "list_groups", {})
    assert sorted(group["name"] for group in groups) == ["Tariffs", "tariff"]


async def test_another_spelling_of_a_group_is_that_group(tool_server) -> None:
    await _call(tool_server, "create_group", {"name": "Crypto"})

    again = await _call(tool_server, "create_group", {"name": " crypto "})

    assert (again["group"], again["already_existed"]) == ("Crypto", True)


async def test_tracking_under_a_lookalike_group_is_refused(tool_server, app) -> None:
    app.state.provider = fakes.FakeProvider(by_slug={"an-event": fakes.event_payload()})
    await _call(tool_server, "create_group", {"name": "Tariffs"})

    refused = await _call(tool_server, "track_event", {"reference": "an-event", "group": "tariff"})

    assert refused["similar_groups"] == ["Tariffs"]
    assert await _call(tool_server, "list_tracked_events", {}) == []
