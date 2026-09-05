"""Which caller may reach which surface: Easy Auth authorizes an application, not a route, so this
record is what it cannot express. A path not in it is refused, and raw ASGI because `/mcp` streams."""

from __future__ import annotations

from tc_runtime.caller_access import CallerAccess, Record, Surface, calling_application

__all__ = [
    "OPEN_PATHS",
    "RECORD",
    "REST_PATHS",
    "TOOLS_PREFIX",
    "CallerAccess",
    "Surface",
    "calling_application",
    "surface_for",
]

# Both are outside Easy Auth in production. `/ping` answers a constant, so it can vary with nothing;
# `/ws/candles` cannot carry a header, and its defence is the single-use ticket. Asserted by equality.
OPEN_PATHS = frozenset({"/ping", "/ws/candles"})
# The mount, and everything the MCP transport hangs below it.
TOOLS_PREFIX = "/mcp"
# Every REST path this module publishes, written out rather than read off `app.routes`: a record
# derived from the application can never disagree with it, and disagreeing is the whole job.
REST_PATHS: tuple[str, ...] = (
    "/",
    "/health",
    "/asset-classes",
    "/candles/{symbol}",
    "/candles/{symbol}/forming",
    "/coverage/{symbol}",
    "/deletions",
    "/indicators",
    "/indicators/{symbol}",
    "/instruments",
    "/instruments/search",
    "/jobs",
    "/jobs/estimate",
    "/jobs/{job_id}",
    "/jobs/{job_id}/retry",
    "/pairs",
    "/pairs/{symbol}",
    "/stream-tickets",
    # FastAPI's own, published by the framework rather than by a router. They describe
    # the REST contract, so they belong to the caller that consumes it.
    "/docs",
    "/docs/oauth2-redirect",
    "/redoc",
    "/openapi.json",
)

RECORD = Record(
    open_paths=OPEN_PATHS,
    rest_paths=REST_PATHS,
    tools_prefix=TOOLS_PREFIX,
    starting_detail="the archive is still starting",
)

surface_for = RECORD.surface_for
