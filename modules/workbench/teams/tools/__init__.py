"""The module's access to its tool servers — `market-mcp` and `polymarket-mcp` for
reads, `trading-mcp` for writes — and who gets which tools.

`client.py` is the only place the `mcp` package exists. Everything past this package
speaks `ToolDescriptor`, `ToolOutcome` and `ToolPlan` — which is what keeps a run's own
code from growing an opinion about a protocol it does not own, and lets a second server
join the first without either speaking a word of MCP itself.
"""

from __future__ import annotations

from .assignment import (
    AnnouncedSnapshot,
    ToolNameCollision,
    ToolNoLongerAnnounced,
    ToolPlan,
    and_list,
    announced_snapshot,
    announced_tools_by_server,
    plan_tools,
)
from .client import (
    ToolAccessError,
    ToolDescriptor,
    ToolOutcome,
    ToolOutcomeKind,
    ToolServer,
    ToolServerRegistry,
    ToolServerUnavailable,
)
from .memory import MEMORY_TOOL_NAMES, MemoryScope, MemoryToolSource

__all__ = [
    "MEMORY_TOOL_NAMES",
    "AnnouncedSnapshot",
    "MemoryScope",
    "MemoryToolSource",
    "ToolAccessError",
    "ToolDescriptor",
    "ToolNameCollision",
    "ToolNoLongerAnnounced",
    "ToolOutcome",
    "ToolOutcomeKind",
    "ToolPlan",
    "ToolServer",
    "ToolServerRegistry",
    "ToolServerUnavailable",
    "and_list",
    "announced_snapshot",
    "announced_tools_by_server",
    "plan_tools",
]
