"""The module's access to `market-mcp`: the session, and who gets which tools.

`client.py` is the only place the `mcp` package exists. Everything past this package
speaks `ToolDescriptor`, `ToolOutcome` and `ToolPlan` — which is what keeps a run's own
code from growing an opinion about a protocol it does not own.

Unlike `agent`, there are no locally implemented tools here: this phase reads the market
through market-mcp and writes nothing at all (proposal.md, "Faza 1 nie składa zleceń").
"""

from __future__ import annotations

from .assignment import ToolNoLongerAnnounced, ToolPlan, announced_tool_names, plan_tools
from .client import (
    ToolAccessError,
    ToolDescriptor,
    ToolOutcome,
    ToolOutcomeKind,
    ToolServer,
    ToolServerUnavailable,
)

__all__ = [
    "ToolAccessError",
    "ToolDescriptor",
    "ToolNoLongerAnnounced",
    "ToolOutcome",
    "ToolOutcomeKind",
    "ToolPlan",
    "ToolServer",
    "ToolServerUnavailable",
    "announced_tool_names",
    "plan_tools",
]
