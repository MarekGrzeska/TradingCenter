"""Liveness, and the one route beside it that does depend on something: `/health` asks the database,
which is why the deploy reads `/` instead."""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(tags=["meta"])


@router.get("/")
async def root() -> dict:
    """What `deploy_probe.py` reads to tell this module from another one on the same plan.

    Reads no database and speaks to no upstream: the deploy asks whether the process inside the
    container came up, and a busy database would answer a different question.
    """
    return {"service": "telegram-gateway", "docs": "/docs"}


@router.get("/health")
async def health(request: Request) -> dict:
    """Whether this gateway can answer at all, which means whether its database can. Not what the
    deploy reads: a slow query would have it call a serving process dead."""
    async with request.app.state.pool.acquire() as conn:
        await conn.fetchval("SELECT 1")
    return {"database": "reachable"}


@router.get("/ping")
async def ping() -> dict:
    """Proves only that the process is up and serving. The response never varies with what the
    module holds, which is what lets Easy Auth exempt it without exposing anything."""
    return {"status": "ok"}
