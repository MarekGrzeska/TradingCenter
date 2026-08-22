"""The read-only tool surface, registered onto one FastMCP instance.

Every tool here reads. Nothing activates a strategy, writes a parameter set, or runs a
backtest — those are the operator's, over REST (`strategy-tools`, "Zestaw narzędzi
wyłącznie czyta"), and `tests/test_tools_surface.py` asserts it of the announced list
rather than trusting this sentence.
"""

from __future__ import annotations

from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP


@dataclass(frozen=True)
class ToolContext:
    """What a tool needs to answer, held as the application rather than its state.

    The state does not exist when the surface is built — the lifespan fills it, long after
    `create_app()` has run — so a tool reaches `app.state` at call time, never at
    registration time.
    """

    app: object

    @property
    def pool(self):
        return self.app.state.pool  # type: ignore[attr-defined]


def register(mcp: FastMCP, context: ToolContext) -> None:
    """Every tool this module announces, in one place so the list is readable as a list.

    Empty until the store these read exists: the transport, the mount and the caller
    record are this module's plumbing and arrive with its skeleton, while what they carry
    arrives with the decisions it reads.
    """
