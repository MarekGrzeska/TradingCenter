"""The read-only tool surface, registered onto one FastMCP instance. Nothing here activates a strategy,
writes a parameter set or runs a backtest, and the surface test asserts that of the announced list."""

from __future__ import annotations

from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP


@dataclass(frozen=True)
class ToolContext:
    """What a tool needs to answer, held as the application rather than its state: the state does not exist
    when the surface is built, so a tool reaches `app.state` at call time."""

    app: object

    @property
    def pool(self):
        return self.app.state.pool  # type: ignore[attr-defined]


def register(mcp: FastMCP, context: ToolContext) -> None:
    """Every tool this module announces, in one place so the list is readable as a list."""
    from . import platform

    platform.register(mcp, context)
