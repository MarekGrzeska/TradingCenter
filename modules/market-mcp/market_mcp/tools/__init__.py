"""The tool surface, one submodule per concern — mirrors market-data's own
`routers/` split (`candles.py`, `indicators.py`, `instruments.py`, ...): a file per
concern rather than one file for the whole surface, so a concern this size stays
readable on its own.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..client import UpstreamClient
from . import candles, indicators, instruments, pairs


def register(mcp: FastMCP, upstream: UpstreamClient) -> None:
    pairs.register(mcp, upstream)
    candles.register(mcp, upstream)
    instruments.register(mcp, upstream)
    indicators.register(mcp, upstream)
