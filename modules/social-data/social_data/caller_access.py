"""Which caller may reach which surface. Nothing on either of them writes, so what this record protects is not the
archive but the split: Easy Auth authorizes an application, so a caller admitted to the tools is otherwise past every
REST route in the same process — including the ones the operator's screens were the audience for."""

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

# Reachable with no identity even where the requirement is on, and both excluded from Easy Auth in
# production. `/` names this module for the deploy probe; `/ping` reads nothing. Asserted by equality.
OPEN_PATHS = frozenset({"/", "/ping"})
TOOLS_PREFIX = "/mcp"
# Every REST path this module publishes, written out rather than read off `app.routes`: a record
# derived from the application can never disagree with it, and disagreeing is the whole job.
REST_PATHS: tuple[str, ...] = (
    "/health",
    "/posts",
    "/posts/{source}/{external_id}",
    "/state",
    # FastAPI's own, published by the framework rather than by a router. They describe the
    # REST contract, so they belong to the caller that consumes it.
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
