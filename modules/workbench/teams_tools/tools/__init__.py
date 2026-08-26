"""Every tool this module publishes, registered in one place. The catalogue is deliberately smaller than
the surface it sits on: a model handed thirty-six tools spends its turns choosing between them."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import TeamsClient
from . import catalogue, runs, schedules


def register(mcp: FastMCP, teams: TeamsClient) -> None:
    catalogue.register(mcp, teams)
    runs.register(mcp, teams)
    schedules.register(mcp, teams)
