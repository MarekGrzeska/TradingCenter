"""Every tool this module publishes, registered in one place.

The catalogue is deliberately smaller than the surface it sits on: `teams` publishes
thirty-six routes, and a model handed thirty-six tools spends its turns choosing between
them rather than doing the work. These are grouped by what the operator is trying to do —
build a team, run it, read what happened, put it on a clock — which is the grouping the
conversation already has (specs/teams-mcp-tools, "Zestaw jest zredukowany do zadań
operatora").
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import TeamsClient
from . import catalogue, runs, schedules


def register(mcp: FastMCP, teams: TeamsClient) -> None:
    catalogue.register(mcp, teams)
    runs.register(mcp, teams)
    schedules.register(mcp, teams)
