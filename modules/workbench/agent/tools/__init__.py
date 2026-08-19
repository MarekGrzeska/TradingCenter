"""The agent's tools: a session with `market-mcp`, and the shapes a turn sees.

`client.py` is the only place the `mcp` package exists, the same way `provider.py` is
the only place langchain's message classes do. Everything past this package speaks
`ToolDescriptor` and `ToolOutcome`.

`chart.py` and `drawings.py` are the exception the specs name: tools this module owns and
executes itself, speaking the same two shapes so the turn cannot tell the difference.

`registry.py` is what the rest of the module now holds instead of a single `ToolServer` —
same four methods, several servers behind them, each configured and each failing on its
own (specs/agent-tool-access).
"""

from __future__ import annotations

from .chart import CHART_TOOL, CHART_TOOL_NAME, ChartTool
from .client import (
    OPERATOR_TOKEN_HEADER,
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
    "OPERATOR_TOKEN_HEADER",
    "ChartTool",
    "DrawOnChartTool",
    "ListChartDrawingsTool",
    "ToolDescriptor",
    "ToolOutcome",
    "ToolOutcomeKind",
    "ToolServer",
    "ToolServerRegistry",
]
