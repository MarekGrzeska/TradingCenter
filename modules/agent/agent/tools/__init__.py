"""The agent's tools: a session with `market-mcp`, and the shapes a turn sees.

`client.py` is the only place the `mcp` package exists, the same way `provider.py` is
the only place langchain's message classes do. Everything past this package speaks
`ToolDescriptor` and `ToolOutcome`.

`chart.py` is the exception the specs name: a tool this module owns and executes itself,
speaking the same two shapes so the turn cannot tell the difference.
"""

from __future__ import annotations

from .chart import CHART_TOOL, CHART_TOOL_NAME, ChartTool
from .client import (
    ToolDescriptor,
    ToolOutcome,
    ToolOutcomeKind,
    ToolServer,
)

__all__ = [
    "CHART_TOOL",
    "CHART_TOOL_NAME",
    "ChartTool",
    "ToolDescriptor",
    "ToolOutcome",
    "ToolOutcomeKind",
    "ToolServer",
]
