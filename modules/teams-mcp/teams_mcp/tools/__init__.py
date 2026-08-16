"""Every tool this module publishes, registered in one place.

The catalogue is deliberately smaller than the surface it sits on: `teams` publishes
thirty-six routes, and a model handed thirty-six tools spends its turns choosing between
them. These are grouped by what the operator is trying to do — see each module's own
docstring (specs/teams-mcp-tools, "Zestaw jest zredukowany do zadań operatora").
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import TeamsClient


def register(mcp: FastMCP, teams: TeamsClient) -> None:
    # Filled in by group 4; the skeleton starts and answers /health without any tool,
    # which is what group 2's tests check.
    return
