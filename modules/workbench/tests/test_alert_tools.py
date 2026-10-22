"""The read-only half of the process's tool surface as the alerts package is handed it: built from the servers the
assembly actually mounts, so a tool a rule is offered is a tool that exists."""

from __future__ import annotations

import pytest

from alerts.catalog import number_fields, usable
from workbench.alert_tools import AlertTools


@pytest.fixture(scope="module")
def tools() -> AlertTools:
    import workbench.app as assembly

    return AlertTools(
        {
            "market-data": assembly.market_app.state.mcp_server,
            "polymarket-data": assembly.polymarket_app.state.mcp_server,
            "social-data": assembly.social_app.state.mcp_server,
        }
    )


async def test_the_price_of_a_pair_is_offered_with_its_numbers(tools: AlertTools) -> None:
    offered = {tool.name: tool for tool in await tools.tools()}

    assert usable(offered["get_last_price"])
    assert offered["get_last_price"].source == "market-data"
    assert "close" in number_fields(offered["get_last_price"].output_schema)


async def test_no_name_is_offered_twice_and_no_writing_tool_can_be_called(tools: AlertTools) -> None:
    offered = await tools.tools()
    writing = [tool.name for tool in offered if not usable(tool)]

    assert len({tool.name for tool in offered}) == len(offered)
    for name in writing:
        assert (await tools.call(name, {})).kind == "refused"


async def test_an_unknown_name_is_refused_rather_than_raised(tools: AlertTools) -> None:
    assert (await tools.call("no_such_tool", {})).kind == "refused"


async def test_a_read_that_asks_a_provider_each_time_is_not_offered_to_a_rule(tools: AlertTools) -> None:
    from workbench.alert_tools import LIVE_READS

    assert not {tool.name for tool in await tools.tools()} & LIVE_READS
    assert (await tools.call("search_events", {"query": "x"})).kind == "refused"
