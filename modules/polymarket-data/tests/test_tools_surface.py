"""What the tool surface announces, what it costs to announce it, and the boundary that
makes three writing tools acceptable in a module whose neighbour publishes none.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

import fakes
import pytest

from polymarket_data import parsing, store
from polymarket_data.models import Sample, Surface

pytestmark = pytest.mark.db

READ_TOOLS = {
    "search_events",
    "browse_events",
    "list_tracked_events",
    "get_event",
    "get_price_history",
    "get_price_changes",
}

# The three that change the list of observations — and the whole list of what this surface
# may change. A fourth appearing here without a decision is what the equality below catches.
OBSERVATION_TOOLS = {"track_event", "untrack_event", "create_group"}

EXPECTED_TOOLS = READ_TOOLS | OBSERVATION_TOOLS

# Characters of the serialized `list_tools()`, which is what an MCP client reads before every
# turn of a conversation — and this is the third such surface in the system, so its size adds
# to two others. In characters rather than tokens so the test needs no tokenizer; the ratio
# measured on this material elsewhere in this repository is a steady 4,2.
#
# Raising it is a deliberate edit of this line, never a side effect of adding a tool.
#
# Measured 13 811 characters on 22 August 2026 for nine tools — about 3 300 tokens, against
# market-data's 19 700 for eleven. The headroom below is 12%: enough for a description to
# grow a sentence that earns it, not enough for the essays to arrive.
SURFACE_CEILING_CHARS = 15_500


async def test_the_expected_tools_and_no_others(tool_server) -> None:
    tools = await tool_server.list_tools()
    assert {tool.name for tool in tools} == EXPECTED_TOOLS


async def test_only_the_three_observation_tools_are_declared_as_changing_anything(
    tool_server,
) -> None:
    """The annotation is a structural claim an MCP client can act on, so it has to be exact.

    `market-data` publishes no writing tool at all and says in its spec that no setting may
    add one. This module departs from that on purpose and in one direction only: the list of
    observations, which is what the operator clicks in the terminal anyway.
    """
    tools = await tool_server.list_tools()
    writing = {
        tool.name
        for tool in tools
        if tool.annotations is not None and tool.annotations.readOnlyHint is False
    }
    assert writing == OBSERVATION_TOOLS


async def test_nothing_on_this_surface_is_declared_destructive(tool_server) -> None:
    """Exact rather than optimistic: starting an observation adds, ending one stops sampling
    and keeps every sample, and creating a group is idempotent. The one operation here that
    loses data is not on this surface at all."""
    for tool in await tool_server.list_tools():
        assert tool.annotations is None or tool.annotations.destructiveHint is False


async def test_no_tool_can_remove_a_single_collected_price(tool_server, pool) -> None:
    """The boundary, tested by running the whole surface rather than by reading its source.

    Every tool is called with arguments that would plausibly reach data, including the three
    that write, and the archive is counted before and after. Deleting collected history is a
    route on the REST contract precisely because it is the one act nobody can undo.
    """
    payload = fakes.event_payload()
    async with pool.acquire() as conn:
        event_id = await store.upsert_event(conn, parsing.event_from(payload))
        outcomes = await store.outcomes_of_event(conn, event_id)
        await store.record_samples(
            conn,
            [
                Sample(outcome_id=outcome_id, observed_at=datetime.now(UTC),
                       midpoint=Decimal("0.5"), source=Surface.GAMMA)
                for outcome_id, _, _ in outcomes
            ],
        )
        await store.record_collected(
            conn, outcomes[0][0], datetime.now(UTC), datetime.now(UTC)
        )
        before = (
            await conn.fetchval("SELECT count(*) FROM price_samples"),
            await conn.fetchval("SELECT count(*) FROM collected_ranges"),
        )

    calls = {
        "search_events": {"query": "anything"},
        "browse_events": {},
        "list_tracked_events": {},
        "get_event": {"event_id": "e-1"},
        "get_price_history": {"outcome_id": outcomes[0][0]},
        "get_price_changes": {"event_id": "e-1"},
        "track_event": {"reference": "an-event"},
        "untrack_event": {"event_id": "e-1"},
        "create_group": {"name": "anything"},
    }
    assert set(calls) == EXPECTED_TOOLS, "every published tool has to be exercised here"
    for name, arguments in calls.items():
        await tool_server.call_tool(name, arguments)

    async with pool.acquire() as conn:
        after = (
            await conn.fetchval("SELECT count(*) FROM price_samples"),
            await conn.fetchval("SELECT count(*) FROM collected_ranges"),
        )
    assert after == before, "a tool removed collected data, which no tool may do"


async def test_every_price_field_says_it_is_a_probability(tool_server) -> None:
    """0,62 read as 62 is wrong by two orders of magnitude without one error on the way, so
    the scale is said where the field is read rather than once in the instructions."""
    for tool in await tool_server.list_tools():
        schema = json.dumps(
            {"in": tool.inputSchema, "out": tool.outputSchema, "doc": tool.description}
        )
        if '"price"' in schema or "probability" in schema.lower():
            assert "0..1" in schema, f"{tool.name} carries a price without naming its scale"


async def test_the_surface_stays_under_its_ceiling(tool_server) -> None:
    tools = await tool_server.list_tools()
    measured = len(
        json.dumps([tool.model_dump(mode="json", exclude_none=True) for tool in tools])
    )
    assert measured <= SURFACE_CEILING_CHARS, (
        f"the tool surface is {measured} characters, above the {SURFACE_CEILING_CHARS} "
        "ceiling. Shorten a description, drop a field, or raise the ceiling on purpose."
    )


async def test_the_instructions_say_what_the_surface_will_not_do(tool_server) -> None:
    """The one sentence a client reads before any tool: three tools change what is
    collected, none deletes it, and nothing here touches an account."""
    instructions = (tool_server.instructions or "").lower()
    assert "0..1" in instructions
    assert "delet" in instructions
    assert "account" in instructions
