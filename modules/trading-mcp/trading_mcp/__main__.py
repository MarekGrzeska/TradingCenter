"""Entry point: `python -m trading_mcp`.

One transport, one mode — see `server.py`'s docstring for why there is no `stdio` to
choose between. The demo-environment check runs before uvicorn starts listening: a
process that never opens a port cannot be reached by anything, which is a stronger
guarantee than refusing inside the first request (specs/trading-mcp-upstream-access,
"Moduł pracuje wyłącznie na rachunku demonstracyjnym").
"""

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
