"""Liveness, and what the archive is currently doing."""

from __future__ import annotations

from fastapi import (
    APIRouter,
    Request,
)

from ..ingest import Ingest

router = APIRouter()


@router.get("/", tags=["meta"])
async def root() -> dict:
    return {"service": "market-data", "docs": "/docs"}


@router.get("/health", tags=["meta"])
async def health(request: Request) -> dict:
    """Whether the archive can answer at all, which means whether its database can."""
    async with request.app.state.pool.acquire() as conn:
        await conn.fetchval("SELECT 1")
    ingest: Ingest = request.app.state.ingest
    return {
        "database": "reachable",
        "collecting": len(ingest.running),
        "started_at": ingest.started_at.isoformat() if ingest.started_at else None,
    }


@router.get("/ping", tags=["meta"])
async def ping() -> dict:
    """Proves only that the process is up and serving — nothing about its dependencies.

    Reads nothing: `/health` above already answers whether the database is reachable, and
    an external prober checking that would read a healthy process as dead the moment a
    query ran slow. This is what Easy Auth's `excluded_paths` (infra/app-service.tf) can
    exempt without exposing anything — the response never varies with the archive's state.
    """
    return {"status": "ok"}
