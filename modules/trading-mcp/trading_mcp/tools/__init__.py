"""The tool surface, one submodule per concern — mirrors market-mcp's own
`tools/` split (specs/trading-mcp-tools).
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import GatewayClient
from . import account, instruments, orders


def register(mcp: FastMCP, gateway: GatewayClient) -> None:
    account.register(mcp, gateway)
    instruments.register(mcp, gateway)
    orders.register(mcp, gateway)
