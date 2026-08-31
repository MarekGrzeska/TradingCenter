"""The module's access to its tool servers, and who gets which tools. `client.py` is the only place the
`mcp` package exists, which is what lets a second server join the first without a run learning a protocol."""

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
