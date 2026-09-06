"""The one shape a tool's refusal takes. The MCP server turns any exception into `isError=True`
carrying `str(exception)`, so what matters is the message: it MUST say what to change."""

from __future__ import annotations


class ToolRefusal(Exception):
    """Raised by a tool to refuse a request it understood but will not serve as asked."""
