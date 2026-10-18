"""Which caller may reach which surface. Easy Auth authorizes an application, not a route, so a caller admitted to the
tools is otherwise past every REST route in the same process — including the ones that write the rules the operator's
screen edits."""

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

# Reachable with no identity even where the requirement is on. `/` names this package for the deploy probe; `/ping`
# reads nothing. Asserted by equality.
OPEN_PATHS = frozenset({"/", "/ping"})
TOOLS_PREFIX = "/mcp"
# Every REST path this package publishes, written out rather than read off `app.routes`: a record derived from the
# application can never disagree with it, and disagreeing is the whole job.
REST_PATHS: tuple[str, ...] = (
    "/health",
    "/catalog",
    "/rules",
    "/rules/{rule_id}",
    "/event-types/{name}",
    # FastAPI's own, published by the framework rather than by a router.
    "/docs",
    "/docs/oauth2-redirect",
    "/redoc",
    "/openapi.json",
)

RECORD = Record(
    open_paths=OPEN_PATHS,
    rest_paths=REST_PATHS,
    tools_prefix=TOOLS_PREFIX,
    starting_detail="the alerts package is still starting",
)

surface_for = RECORD.surface_for
