"""What a route reaches for, off the application state the lifespan filled."""

from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from ..problems import Problem

# The columns' own ranges: a number past them is a refusal FastAPI names, not a database error asyncpg raises.
BIGINT = 2**63 - 1
INTEGER = 2**31 - 1


def pool(request: Request):
    return request.app.state.pool


def archive(request: Request):
    return request.app.state.archive


def queue(request: Request):
    return request.app.state.queue


def settings(request: Request):
    return request.app.state.settings


def refused(detail: str, problems: list[Problem], status: int = 422) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": detail, "problems": [p.as_dict() for p in problems]})


def not_found(what: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"{what} does not exist")
