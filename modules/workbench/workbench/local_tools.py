"""A package's tool surface as both registries see it, without the network: the FastMCP server the package
mounts at its own `/mcp`, called as a function. Same names, same descriptions, same refusals — what goes away is
the transport, the address and the identity a session would have carried. One core, two thin faces, because
`agent` and `teams` each have a `ToolDescriptor` and a `ToolOutcome` of their own and neither imports the other's.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from agent.tools import ToolDescriptor as AgentToolDescriptor
from agent.tools import ToolOutcome as AgentToolOutcome
from agent.tools import ToolOutcomeKind as AgentOutcomeKind
from teams.tools.client import ToolDescriptor as TeamsToolDescriptor
from teams.tools.client import ToolOutcome as TeamsToolOutcome
from teams.tools.client import ToolOutcomeKind as TeamsOutcomeKind

log = logging.getLogger(__name__)


class _InProcess:
    """One FastMCP server, asked what it publishes once and called as often as needed."""

    def __init__(self, label: str, server: FastMCP) -> None:
        self.label = label
        self._server = server
        self._published: list[Any] | None = None

    async def tools(self) -> list[Any]:
        if self._published is None:
            self._published = list(await self._server.list_tools())
            log.info("%s: published %d tools in this process", self.label, len(self._published))
        return self._published

    async def call(self, name: str, arguments: dict[str, Any]) -> tuple[str, str, int]:
        """`(kind, text, elapsed_ms)` with kind as the string both enums share."""
        started = time.monotonic()

        def elapsed() -> int:
            return int((time.monotonic() - started) * 1000)

        try:
            result = await self._server.call_tool(name, arguments)
        except ToolError as err:
            # Every refusal a tool writes deliberately arrives wrapped in this, so its own words travel.
            return ("refused", str(err), elapsed())
        except Exception as err:  # noqa: BLE001 - a broken tool is not a broken turn
            log.warning("%s: tool call %s failed: %s", self.label, name, err)
            return (
                "unavailable",
                f"{self.label} could not answer {name!r}: {err}. The call was not made.",
                elapsed(),
            )
        return ("ok", _text_of(result), elapsed())


def _text_of(result: Any) -> str:
    """What the model reads: a `(content, structured)` pair for a tool with an output schema, and the
    structured half is the one — content blocks are one per item, and joining them hands back several documents."""
    if isinstance(result, tuple) and len(result) == 2:
        return json.dumps(result[1])
    if isinstance(result, dict):
        return json.dumps(result)
    return "\n".join(
        block.text for block in result if getattr(block, "type", None) == "text"
    ).strip()


class ConversationLocalTools:
    """The conversation registry's face: a drop-in for a `ToolServer`, always configured, never retried."""

    configured = True

    def __init__(self, label: str, server: FastMCP) -> None:
        self.label = label
        self._core = _InProcess(label, server)

    async def aclose(self) -> None:
        """Nothing of its own to close — the server belongs to the package that mounted it."""

    async def list_tools(self, operator_principal: str | None = None) -> list[AgentToolDescriptor]:
        return [
            AgentToolDescriptor(
                name=tool.name,
                description=tool.description or "",
                input_schema=tool.inputSchema or {},
                read_only=tool.annotations.readOnlyHint if tool.annotations else None,
            )
            for tool in await self._core.tools()
        ]

    def moves_the_account(self, name: str) -> bool:
        return False

    async def call(
        self, name: str, arguments: dict[str, Any], operator_principal: str | None = None
    ) -> AgentToolOutcome:
        kind, text, elapsed = await self._core.call(name, arguments)
        return AgentToolOutcome(AgentOutcomeKind(kind), text, elapsed)


class TeamsLocalTools:
    """The teams registry's face: what `registry.local` holds beside team memory."""

    can_move_the_account = False
    configured = True

    def __init__(self, label: str, server: FastMCP) -> None:
        self.label = label
        self._core = _InProcess(label, server)

    async def aclose(self) -> None:
        """Nothing of its own to close — the server belongs to the package that mounted it."""

    def bound(self, scope: Any) -> TeamsLocalTools:
        """A run binds its local sources to its own memory scope; these tools have no run-scoped state."""
        return self

    async def list_tools(self) -> list[TeamsToolDescriptor]:
        return [
            TeamsToolDescriptor(
                name=tool.name,
                description=tool.description or "",
                input_schema=tool.inputSchema or {},
                read_only=tool.annotations.readOnlyHint if tool.annotations else None,
            )
            for tool in await self._core.tools()
        ]

    async def call(
        self, name: str, arguments: dict[str, Any], *, agent_key: str | None = None
    ) -> TeamsToolOutcome:
        kind, text, elapsed = await self._core.call(name, arguments)
        return TeamsToolOutcome(TeamsOutcomeKind(kind), text, elapsed)
