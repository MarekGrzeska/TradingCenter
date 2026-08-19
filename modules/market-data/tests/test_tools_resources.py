"""The three resources and the one prompt, read by URI rather than called as tools."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from tools_double import coverage_range, tracked

from market_data.indicators import service

START = datetime(2026, 1, 1, tzinfo=UTC)


async def test_pairs_resource_reads_the_archive(tool_server, archive) -> None:
    archive.pairs = [tracked(symbol="US100"), tracked(symbol="DE40")]

    [content] = await tool_server.read_resource("market://pairs")

    assert [pair["symbol"] for pair in json.loads(content.content)] == ["US100", "DE40"]


async def test_indicators_catalogue_resource(tool_server) -> None:
    [content] = await tool_server.read_resource("market://indicators/catalogue")

    published = json.loads(content.content)
    assert published["algorithm_version"] == service.catalogue().algorithm_version
    assert len(published["indicators"]) == len(service.catalogue().indicators)


async def test_coverage_resource_template_substitutes_symbol_and_resolution(
    tool_server, archive
) -> None:
    archive.with_coverage([coverage_range(START, START.replace(hour=6))])

    [content] = await tool_server.read_resource("market://coverage/US100/HOUR")

    read = json.loads(content.content)
    assert read["resolution"] == "HOUR"
    assert read["symbol"] == "US100"
    assert len(read["ranges"]) == 1


async def test_resources_are_listed(tool_server) -> None:
    resources = [str(r.uri) for r in await tool_server.list_resources()]
    templates = [t.uriTemplate for t in await tool_server.list_resource_templates()]

    assert "market://pairs" in resources
    assert "market://indicators/catalogue" in resources
    assert "market://coverage/{symbol}/{resolution}" in templates


async def test_analyze_symbol_prompt_orders_the_steps(tool_server) -> None:
    result = await tool_server.get_prompt("analyze-symbol", {"symbol": "US100"})

    text = result.messages[0].content.text
    coverage_at = text.index("describe_coverage")
    summary_at = text.index("summarize_range")
    indicators_at = text.index("compute_indicators")
    unknowns_at = text.index("name explicitly what is not known")
    assert coverage_at < summary_at < indicators_at < unknowns_at
    assert "US100" in text
