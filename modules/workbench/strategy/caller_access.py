"""Which caller may reach which surface, which Easy Auth cannot express: it authorizes an application, not a route.
The identity is the calling application read from the token's claims, never the header that names the person."""

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

# `/ping` answers a constant. It reads nothing, so its answer cannot vary with anything this module
# holds. The test on this set asserts equality, so any addition here fails CI.
OPEN_PATHS = frozenset({"/ping"})
TOOLS_PREFIX = "/mcp"
# Every REST path this module publishes, written out rather than read off `app.routes`: a record derived
# from the application can never disagree with it, and disagreeing is the whole job.
REST_PATHS: tuple[str, ...] = (
    "/",
    "/health",
    "/strategies",
    "/strategies/{strategy_id}",
    # The configurator's four. Written rules are the operator's, like every other write
    # here — the workbench reads what a strategy decided and has no business composing one.
    "/definitions",
    "/definitions/{strategy_id}",
    "/definitions/{strategy_id}/revisions",
    "/definitions/{strategy_id}/revisions/{version}",
    "/parameter-sets",
    "/watches",
    "/watches/{watch_id}",
    "/decisions",
    "/decisions/{decision_id}",
    "/backtests",
    "/backtests/{run_id}",
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
    starting_detail="the platform is still starting",
)

surface_for = RECORD.surface_for
