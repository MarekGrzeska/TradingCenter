"""The read-only half of this process's tool surface, as the alerts package asks for it: every package's FastMCP server
called as a function, offering only what says it reads. `alerts` may not import a neighbour, so it describes what it
needs (`alerts.catalog.ToolSource`) and the assembly is where something that fits is built."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from mcp.server.fastmcp import FastMCP

from alerts.catalog import CatalogTool, ToolOutcome

from .local_tools import _InProcess

log = logging.getLogger(__name__)


class AlertTools:
    def __init__(self, servers: Mapping[str, FastMCP]) -> None:
        self._cores = {label: _InProcess(label, server) for label, server in servers.items()}
        self._published: dict[str, CatalogTool] | None = None
        self._owner: dict[str, str] = {}

    async def tools(self) -> list[CatalogTool]:
        return list((await self._catalogue()).values())

    async def call(self, name: str, arguments: dict[str, Any]) -> ToolOutcome:
        tool = (await self._catalogue()).get(name)
        if tool is None:
            return ToolOutcome("refused", f"no tool named {name!r} is offered here")
        # Checked again where the call is made, not only where the rule is written: whatever reaches this far is a read.
        if tool.read_only is not True:
            return ToolOutcome("refused", f"{name!r} is not a tool that only reads")
        kind, text, _ = await self._cores[self._owner[name]].call(name, arguments)
        return ToolOutcome(kind, text)  # pyright: ignore[reportArgumentType]

    async def _catalogue(self) -> dict[str, CatalogTool]:
        if self._published is None:
            found: dict[str, CatalogTool] = {}
            for label, core in self._cores.items():
                for tool in await core.tools():
                    if tool.name in found:
                        # Two packages with one name would make a rule's `tool_name` ambiguous; the first keeps it.
                        log.warning("tool %s is offered by %s and by %s; a rule reads the first", tool.name, self._owner[tool.name], label)
                        continue
                    self._owner[tool.name] = label
                    found[tool.name] = CatalogTool(
                        name=tool.name,
                        description=tool.description or "",
                        source=label,
                        input_schema=tool.inputSchema or {},
                        output_schema=tool.outputSchema,
                        read_only=tool.annotations.readOnlyHint if tool.annotations else None,
                    )
            self._published = found
        return self._published
