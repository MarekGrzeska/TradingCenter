"""Liveness, and what the platform is currently watching."""

from __future__ import annotations

from fastapi import APIRouter, Request


def loops(request) -> dict:
    """How long since each of this module's loops last finished a pass. On `/health` and never on
    `/ping`: this is the module's own work going well, which is a different question from whether
    the process is alive, and a probe that conflates them reddens for the wrong reason."""
    heartbeats = getattr(request.app.state, "heartbeats", None)
    return {} if heartbeats is None else heartbeats.as_dict()


router = APIRouter()


@router.get("/", tags=["meta"])
async def root() -> dict:
    return {"service": "strategy", "docs": "/docs"}


@router.get("/health", tags=["meta"])
async def health(request: Request) -> dict:
    """Whether the platform can answer at all, which means whether its database can.

    `watching` is a count and never a requirement: zero is a supported state, not a
    degraded one (`strategy-runtime`, "Platforma bez strategii jest stanem wspieranym").
    """
    async with request.app.state.pool.acquire() as conn:
        watching = await conn.fetchval("SELECT count(*) FROM watches WHERE active")
    loop = getattr(request.app.state, "loop", None)
    return {
        "database": "reachable",
        "watching": int(watching or 0),
        "evaluating": bool(loop and loop.running),
        "loops": loops(request),
    }


@router.get("/ping", tags=["meta"])
async def ping() -> dict:
    """Proves only that the process is up and serving — nothing about its dependencies.

    Reads nothing: `/health` above already answers whether the database is reachable, and
    an external prober checking that would read a healthy process as dead the moment a
    query ran slow. This is what Easy Auth's `excluded_paths` can exempt without exposing
    anything — the response never varies with this module's state.
    """
    return {"status": "ok"}
