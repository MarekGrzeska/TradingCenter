"""One FastMCP instance, mounted at `/mcp` in this module's own application.

It was a separate process until 19 August 2026, and what it lost in becoming a route is
the scaffolding of that separation: an HTTP client to this module, a committed copy of
this module's schema, and the script that policed the copy. What it kept is every tool,
every ceiling and every sentence about uncertainty.

`/health` is left to `routers/meta.py`: the platform's probe reaches this application, not
this route, and one module answering two health paths is one more thing to keep in step.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from starlette.types import ASGIApp
from tc_mcp_kit.tool_schemas import slim_tool_schemas

from . import tools
from .tools import ToolContext

INSTRUCTIONS = (
    "Read-only tools over this archive's candles and indicator catalogue. No tool here "
    "changes state: starting collection on a pair, or deleting one, happens in the "
    "terminal, never through this server."
)


def build_server(app) -> FastMCP:
    mcp = FastMCP("market-data", instructions=INSTRUCTIONS)

    tools.register(mcp, ToolContext(app=app))

    # Every tool's schema, minus what pydantic writes for its own sake: field titles
    # repeating field names, an `anyOf` of bare types where a type list says the same, and
    # defaults on a reply nobody constructs. 22,6% of what this process announces in every
    # turn of a conversation, and not one field, type or `required` entry with it
    # (specs/market-data-tools, "Powierzchnia narzędzi ma zapisany sufit").
    slim_tool_schemas(mcp)

    return mcp


def build_mcp_app(app) -> ASGIApp:
    """The streamable-http transport, to be mounted under `/mcp`.

    Unwrapped by anything here: the caller-identity check is one layer in front of the
    whole application (`caller_access.py`), because this module has a REST surface beside
    this one and the two need one answer to "who is calling", not two.
    """
    return build_server(app).streamable_http_app()
