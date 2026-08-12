"""Entry point: `python -m market_mcp [stdio|http]`.

Defaults to `stdio` — the transport with no port to remember, because that is the one a
client on a desk expects (a Claude Desktop config hands it input on stdin). `http` is
what the deployed instance runs, one process serving both `/mcp` and `/health`.
"""

from __future__ import annotations

import argparse
import asyncio

import uvicorn

from .client import UpstreamClient
from .config import Settings
from .server import build_http_app, build_server


async def _serve(transport: str) -> None:
    settings = Settings()
    upstream = UpstreamClient(settings)
    try:
        if transport == "stdio":
            mcp = build_server(settings, upstream)
            await mcp.run_stdio_async()
        else:
            # Not `mcp.run_streamable_http_async()`: that builds the transport's own
            # ASGI app internally, with no seam to wrap it in the caller-identity
            # check `build_http_app` adds (task 5.2).
            app = build_http_app(settings, upstream)
            config = uvicorn.Config(app, host=settings.mcp_http_host, port=settings.mcp_http_port)
            await uvicorn.Server(config).serve()
    finally:
        await upstream.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(prog="market-mcp")
    parser.add_argument("transport", choices=["stdio", "http"], nargs="?", default="stdio")
    args = parser.parse_args()
    asyncio.run(_serve(args.transport))


if __name__ == "__main__":
    main()
