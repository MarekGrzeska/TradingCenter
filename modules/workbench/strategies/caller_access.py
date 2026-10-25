"""Which caller may reach which surface. This package publishes REST alone: its tools are called as functions by the
conversation in this process and never mounted, so nothing reaches them through this door."""

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
    "/runs",
    "/runs/{run_id}",
    "/runs/{run_id}/cancel",
    "/runs/{run_id}/trades",
    "/costs",
    "/costs/{symbol}",
    # FastAPI's own, published by the framework rather than by a router.
    "/docs",
    "/docs/oauth2-redirect",
    "/redoc",
    "/openapi.json",
)

RECORD = Record(
    open_paths=OPEN_PATHS,
    rest_paths=REST_PATHS,
    tools_prefix=None,
    starting_detail="the strategy engine is still starting",
)

surface_for = RECORD.surface_for
