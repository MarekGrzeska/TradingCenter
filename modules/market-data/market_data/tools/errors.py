"""The one shape a tool's refusal takes.

Raising `ToolRefusal` inside a tool function is enough: the MCP server converts any
exception a tool raises into `isError=True`, carrying `str(exception)` as the content
— so what matters here is the message. It MUST say what to change for the request to
succeed (specs/market-data-answers, "Odmowa jest odpowiedzią o jednym kształcie").
"""

from __future__ import annotations


class ToolRefusal(Exception):
    """Raised by a tool to refuse a request it understood but will not serve as asked."""
