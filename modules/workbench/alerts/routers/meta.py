"""Liveness. What the package is currently doing is `/state`, which arrives with the contract."""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


def loops(request: Request) -> dict:
    """How long since each of this package's loops last finished a pass. On `/health` and never on `/ping`: this is the
    package's own work going well, a different question from whether the process is alive, and a probe that conflates
    them reddens for the wrong reason."""
    heartbeats = getattr(request.app.state, "heartbeats", None)
    return {} if heartbeats is None else heartbeats.as_dict()


@router.get("/", tags=["meta"])
async def root() -> dict:
    """What `deploy_probe.py` reads to tell this package from another one on the same plan."""
    return {"service": "alerts", "docs": "/docs"}


@router.get("/health", tags=["meta"])
async def health(request: Request) -> dict:
    """Whether the package can answer at all, which means whether its database can."""
    async with request.app.state.pool.acquire() as conn:
        await conn.fetchval("SELECT 1")
    return {"database": "reachable", "loops": loops(request)}


@router.get("/ping", tags=["meta"])
async def ping() -> dict:
    """Proves only that the process is up and serving — nothing about its dependencies, so Easy Auth can exempt it
    without exposing anything."""
    return {"status": "ok"}
