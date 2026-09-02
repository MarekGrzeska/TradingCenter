"""Which caller may reach which surface. The boundary is not `market-data`'s, and the difference is the point: three
tools here write by design, so what the record protects is deleting collected history, the one act nobody can undo."""

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
    "/events",
    "/events/{provider_event_id}",
    "/events/{provider_event_id}/tracking",
    "/events/{provider_event_id}/history",
    "/events/{provider_event_id}/changes",
    "/events/{event_id}/group",
    "/groups",
    "/groups/{group_id}",
    "/outcomes/{outcome_id}/history",
    "/snapshot",
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
