"""Liveness, and — from the `/state` route added with the contract — what the archive is currently doing."""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/", tags=["meta"])
async def root() -> dict:
    """What `deploy_probe.py` reads to tell this module from another one on the same plan."""
    return {"service": "social-data", "docs": "/docs"}


@router.get("/health", tags=["meta"])
async def health(request: Request) -> dict:
    """Whether the archive can answer at all, which means whether its database can."""
    async with request.app.state.pool.acquire() as conn:
        await conn.fetchval("SELECT 1")
    return {"database": "reachable"}


@router.get("/ping", tags=["meta"])
async def ping() -> dict:
    """Proves only that the process is up and serving — nothing about its dependencies.

    Reads nothing, so Easy Auth can exempt it without exposing anything: `/health` above is
    the route that answers whether the database is reachable, and an external prober reading
    that would call a healthy process dead the moment one query ran slow.
    """
    return {"status": "ok"}
