"""The conversation's tools: sessions with the servers that have one, and the shapes a
turn sees.

`client.py` is the only place the `mcp` package exists, the same way `provider.py` is
the only place langchain's message classes do. Everything past this package speaks
`ToolDescriptor` and `ToolOutcome`.

`chart.py` and `drawings.py` are the exception the specs name: tools this module owns and
executes itself, speaking the same two shapes so the turn cannot tell the difference.

`registry.py` is what the rest of the package holds instead of a single `ToolServer` —
same four methods, several sources behind them, each configured and each failing on its
own (specs/agent-tool-access). One of those sources is not a server at all: the team tools
run in this process, and the registry is handed one built by the assembly.
"""

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
