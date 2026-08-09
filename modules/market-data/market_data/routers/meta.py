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
