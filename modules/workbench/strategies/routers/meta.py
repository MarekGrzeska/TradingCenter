"""Liveness."""

from __future__ import annotations

from fastapi import APIRouter, Request

from .. import runs
from ..contract import HealthOut

router = APIRouter()


@router.get("/", tags=["meta"])
async def root() -> dict:
    """What `deploy_probe.py` reads to tell this package from another one on the same plan."""
    return {"service": "strategies", "docs": "/docs"}


@router.get("/health", tags=["meta"], response_model=HealthOut)
async def health(request: Request) -> HealthOut:
    """Whether the package can answer at all — its database — and what its queue holds."""
    async with request.app.state.pool.acquire() as conn:
        waiting = await runs.queued(conn)
    running = request.app.state.queue.busy
    return HealthOut.model_validate({
        "database": "reachable",
        "queue": {"queued": waiting, "running": running},
        "max_minute_bars": request.app.state.settings.max_minute_bars,
    })


@router.get("/ping", tags=["meta"])
async def ping() -> dict:
    """Proves only that the process is up and serving — nothing about its dependencies."""
    return {"status": "ok"}
