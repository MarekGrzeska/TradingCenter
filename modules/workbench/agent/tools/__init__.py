"""The conversation's tools: sessions with the servers that have one, and the shapes a turn sees. `client.py` is the
only place the `mcp` package exists; `registry.py` holds several sources, one of them not a server at all."""

from __future__ import annotations

from .chart import CHART_TOOL, CHART_TOOL_NAME, ChartTool
from .client import (
    ToolDescriptor,
    ToolOutcome,
    ToolOutcomeKind,
    ToolServer,
)
from .drawings import (
    DRAW_TOOL,
    DRAW_TOOL_NAME,
    LIST_DRAWINGS_TOOL,
    LIST_DRAWINGS_TOOL_NAME,
    DrawOnChartTool,
    ListChartDrawingsTool,
)
from .registry import ToolServerRegistry

__all__ = [
    "CHART_TOOL",
    "CHART_TOOL_NAME",
    "DRAW_TOOL",
    "DRAW_TOOL_NAME",
    "LIST_DRAWINGS_TOOL",
    "LIST_DRAWINGS_TOOL_NAME",
    "ChartTool",
    "DrawOnChartTool",
    "ListChartDrawingsTool",
    "ToolDescriptor",
    "ToolOutcome",
    "ToolOutcomeKind",
    "ToolServer",
    "ToolServerRegistry",
]
