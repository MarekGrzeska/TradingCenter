"""Which caller may reach which surface. Both of them send, so the split this record keeps is not reading
from writing: it is that creating a bot and binding a destination are REST alone. Easy Auth authorizes an
application and not a route, so without this a caller admitted to the tools is past every route here."""

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
    "/state",
    "/messages",
    "/bots",
    "/bots/adopted",
    "/bots/created",
    "/bots/{username}",
    "/destinations",
    "/destinations/{name}",
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
    starting_detail="the gateway is still starting",
)

surface_for = RECORD.surface_for
