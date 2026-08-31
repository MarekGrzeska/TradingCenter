"""Liveness, and nothing that depends on anything."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["meta"])


@router.get("/")
async def root() -> dict:
    """What `deploy_probe.py` reads to tell this module from another one on the same plan.

    Reads no database and speaks to no upstream: the deploy asks whether the process inside the
    container came up, and a busy database would answer a different question.
    """
    return {"service": "telegram-gateway", "docs": "/docs"}


@router.get("/ping")
async def ping() -> dict:
    """Proves only that the process is up and serving. The response never varies with what the
    module holds, which is what lets Easy Auth exempt it without exposing anything."""
    return {"status": "ok"}
