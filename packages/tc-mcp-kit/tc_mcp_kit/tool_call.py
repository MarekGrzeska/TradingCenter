"""The HTTP request behind the tool call being served. Read from the MCP request context, not from a context variable set
around the HTTP request: in stateful streamable-http a tool runs in the session's task, which never sees one."""

from __future__ import annotations

from mcp.server.lowlevel.server import request_ctx


def request_header(name: str) -> str | None:
    """`None` outside a tool call served over HTTP — in a test calling the server directly, or over stdio."""
    try:
        request = request_ctx.get().request
    except LookupError:
        return None
    headers = getattr(request, "headers", None)
    return headers.get(name) if headers is not None else None
