"""The agent's tools: a session with `market-mcp`, and the shapes a turn sees.

`client.py` is the only place the `mcp` package exists, the same way `provider.py` is
the only place langchain's message classes do. Everything past this package speaks
`ToolDescriptor` and `ToolOutcome`.
"""

from __future__ import annotations

from .client import (
    ToolDescriptor,
    ToolOutcome,
    ToolOutcomeKind,
    ToolServer,
)

__all__ = [
    "ToolDescriptor",
    "ToolOutcome",
    "ToolOutcomeKind",
    "ToolServer",
]
