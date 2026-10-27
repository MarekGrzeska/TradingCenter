"""Which caller may reach which surface: REST for the operator's screen, `/mcp` for the operator's own MCP client. The
conversation calls the same tools as functions in this process and never passes this door."""

from __future__ import annotations

from tc_runtime.caller_access import CallerAccess, Record, Surface, calling_application

__all__ = [
    "OPEN_PATHS",
    "RECORD",
    "REST_PATHS",
    "CallerAccess",
    "Surface",
    "calling_application",
    "surface_for",
]

# Reachable with no identity even where the requirement is on. `/` names this package for the deploy probe; `/ping`
# reads nothing. Asserted by equality.
OPEN_PATHS = frozenset({"/", "/ping"})
# Every REST path this package publishes, written out rather than read off `app.routes`: a record derived from the
# application can never disagree with it, and disagreeing is the whole job.
REST_PATHS: tuple[str, ...] = (
    "/health",
    "/language",
    "/validate",
    "/strategies",
    "/strategies/{strategy_id}",
    "/strategies/{strategy_id}/revisions",
    "/strategies/{strategy_id}/revisions/{n}",
    "/strategies/{strategy_id}/revisions/{n}/changes",
    "/strategies/{strategy_id}/archive",
    "/strategies/{strategy_id}/restore",
    "/strategies/{strategy_id}/conversation",
    "/strategies/{strategy_id}/draft",
    "/drafts/new",
    "/runs",
    "/runs/compare",
    "/runs/{run_id}",
    "/runs/{run_id}/cancel",
    "/runs/{run_id}/trades",
    "/runs/{run_id}/trades.csv",
    "/costs",
    "/costs/{symbol}",
    "/costs/{symbol}/from-broker",
    "/margins/{symbol}",
    # FastAPI's own, published by the framework rather than by a router.
    "/docs",
    "/docs/oauth2-redirect",
    "/redoc",
    "/openapi.json",
)

RECORD = Record(
    open_paths=OPEN_PATHS,
    rest_paths=REST_PATHS,
    tools_prefix="/mcp",
    starting_detail="the strategy engine is still starting",
)

surface_for = RECORD.surface_for
