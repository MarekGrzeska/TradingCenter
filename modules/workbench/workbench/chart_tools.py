"""The conversation's two drawing tools under `/chart-tools/mcp`, for the operator's own MCP client
(`operator-mcp-access`): the same `draw_on_chart` and `list_chart_drawings` a turn calls, over the same table, so a
level drawn from Claude Code stands on the terminal's chart like one the conversation drew. `set_chart` stays out:
it moves one conversation's chart, and a call from outside has no conversation."""

from __future__ import annotations

from typing import Any

import asyncpg
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from starlette.applications import Starlette
from tc_mcp_kit.mounted_server import build_server

from agent.tools import (
    DRAW_TOOL,
    LIST_DRAWINGS_TOOL,
    DrawOnChartTool,
    ListChartDrawingsTool,
    ToolOutcome,
)

from . import tool_surface
from .config import Settings

INSTRUCTIONS = (
    "The objects drawn on the operator's charts: levels, zones and trend lines, one set per instrument, "
    "shown on every chart of that symbol in the terminal and kept until removed. The same drawings the "
    "conversation makes and reads. Read them with list_chart_drawings before removing or hiding anything."
)


def build_chart_server(pool: asyncpg.Pool, archive: Any) -> FastMCP:
    """`archive` is the conversation's own registry, the one a turn checks the symbol through: it answers
    as a `ToolServer` does without being one, as `agent.surface.State` already types it."""
    draw = DrawOnChartTool(pool, archive)
    listing = ListChartDrawingsTool(pool)

    def register(mcp: FastMCP) -> None:
        async def draw_on_chart(
            symbol: str,
            add: list[dict[str, Any]] | None = None,
            remove: list[int] | None = None,
            hide: list[int] | None = None,
            show: list[int] | None = None,
        ) -> str:
            arguments = {"symbol": symbol, "add": add, "remove": remove, "hide": hide, "show": show}
            # No session: a drawing made from outside belongs to no conversation, which the column already allows.
            return _answer(await draw.call(arguments, session_id=None))

        async def list_chart_drawings(symbol: str) -> str:
            return _answer(await listing.call({"symbol": symbol}))

        mcp.add_tool(
            draw_on_chart,
            name=DRAW_TOOL.name,
            description=DRAW_TOOL.description,
            annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False),
        )
        mcp.add_tool(
            list_chart_drawings,
            name=LIST_DRAWINGS_TOOL.name,
            description=LIST_DRAWINGS_TOOL.description,
            annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True),
        )
        # The conversation's own schemas rather than the signatures': `add` is a union of three shapes, each with
        # its own field names, and a client handed `list[object]` would not know them.
        schemas = {d.name: d.input_schema for d in (DRAW_TOOL, LIST_DRAWINGS_TOOL)}
        for tool in mcp._tool_manager.list_tools():
            tool.parameters = schemas[tool.name]

    return build_server("chart-tools", INSTRUCTIONS, register)


def _answer(outcome: ToolOutcome) -> str:
    if not outcome.ok:
        raise ToolError(outcome.text)
    return outcome.text


def create_surface() -> Starlette:
    """Mounted at import, under `/chart-tools`."""
    return tool_surface.create_surface("the chart tools are still starting")


def serving(surface: Starlette, pool: asyncpg.Pool, archive: Any, settings: Settings):
    return tool_surface.serving(surface, build_chart_server(pool, archive), settings)
