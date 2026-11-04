"""Every package's tools reach the conversation through one registry, and a name two of them announce goes to whichever
was listed first: strategies' `read_run` was answered by the teams' one, with a refusal about identity."""

from __future__ import annotations

from collections import Counter

import alerts.app
import market_data.app
import polymarket_data.app
import social_data.app
import strategies.app
import telegram_gateway.app
import youtube_data.app
from teams_tools.server import build_server as build_team_tools


async def test_no_two_packages_offer_the_conversation_the_same_tool_name() -> None:
    servers = [
        build_team_tools(None),  # type: ignore[arg-type]  # listing never reaches the client
        *(
            package.create_app().state.mcp_server
            for package in (
                market_data.app, polymarket_data.app, social_data.app, telegram_gateway.app,
                alerts.app, strategies.app,
            )
        ),
        youtube_data.app.create_app().state.local_mcp_server,
    ]
    names: Counter[str] = Counter()
    for server in servers:
        names.update(tool.name for tool in await server.list_tools())

    assert [name for name, count in names.items() if count > 1] == []
