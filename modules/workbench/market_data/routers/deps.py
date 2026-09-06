"""The two things a route reaches for, and nothing else. Kept apart from `app.py` so a router never
imports the module that mounts it — that cycle is what made one 773-line module feel unavoidable."""

from __future__ import annotations

import asyncio

from fastapi import Request, WebSocket

from ..hub import Hub


def pool(request: Request):
    return request.app.state.pool


def hub(websocket: WebSocket) -> Hub:
    # A WebSocket connection is not a Request: asking for one here leaves FastAPI with
    # nothing to pass, and the handshake fails before it is ever accepted.
    return websocket.app.state.hub


def hub_over_http(request: Request) -> Hub:
    # The same hub, reached the other way. Two functions rather than a union parameter, because
    # FastAPI resolves the dependency by its annotation and cannot hand over a `Request | WebSocket`.
    return request.app.state.hub


def indicator_limiter(request: Request) -> asyncio.Semaphore:
    return request.app.state.indicator_limiter
