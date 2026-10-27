"""Entry point: `python -m trading_mcp`. The demo-environment check runs before uvicorn listens: a
process that never opens a port cannot be reached, which beats refusing inside the first request."""

from __future__ import annotations

import asyncio
import logging

import uvicorn

from .client import GatewayClient
from .config import Settings
from .server import build_http_app


async def _serve() -> None:
    settings = Settings()  # type: ignore[call-arg]
    gateway = GatewayClient(settings)
    try:
        await gateway.ensure_demo_environment()
        app = build_http_app(settings, gateway)
        config = uvicorn.Config(app, host=settings.trading_mcp_host, port=settings.trading_mcp_port)
        await uvicorn.Server(config).serve()
    finally:
        await gateway.aclose()


def main() -> None:
    # Nothing configured logging here before, so every INFO line — the trace of each write among them — went nowhere.
    # This module's own at INFO; the libraries' at WARNING, or httpx writes a line per call to the gateway.
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("trading_mcp").setLevel(logging.INFO)
    asyncio.run(_serve())


if __name__ == "__main__":
    main()
