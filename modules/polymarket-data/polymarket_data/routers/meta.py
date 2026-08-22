"""Liveness, and what the archive is currently doing."""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/", tags=["meta"])
async def root() -> dict:
    """What `deploy_probe.py` reads to tell this module from another one on the same plan."""
    return {"service": "polymarket-data", "docs": "/docs"}


@router.get("/health", tags=["meta"])
async def health(request: Request) -> dict:
    """Whether the archive can answer at all, which means whether its database can."""
    async with request.app.state.pool.acquire() as conn:
        await conn.fetchval("SELECT 1")
    return {"database": "reachable"}


@router.get("/ping", tags=["meta"])
async def ping() -> dict:
    """Proves only that the process is up and serving — nothing about its dependencies.

    Reads nothing: `/health` above already answers whether the database is reachable, and
    an external prober checking that would read a healthy process as dead the moment a
    query ran slow. This is what Easy Auth's `excluded_paths` can exempt without exposing
    anything — the response never varies with what the archive holds.
    """
    return {"status": "ok"}
