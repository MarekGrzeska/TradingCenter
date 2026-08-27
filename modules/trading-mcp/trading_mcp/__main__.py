"""Entry point: `python -m trading_mcp`. The demo-environment check runs before uvicorn listens: a
process that never opens a port cannot be reached, which beats refusing inside the first request."""

from __future__ import annotations

import asyncio

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
    asyncio.run(_serve())


if __name__ == "__main__":
    main()
