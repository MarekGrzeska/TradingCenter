"""The two things a route reaches for, and nothing else.

Kept apart from `app.py` so a router never imports the module that mounts it. That import
would be a cycle, and the shape of the cycle — routes reaching back for the application
object — is what made a single 773-line module feel unavoidable in the first place.
"""

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


def indicator_limiter(request: Request) -> asyncio.Semaphore:
    return request.app.state.indicator_limiter
