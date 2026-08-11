"""Entry point: `python -m market_mcp [stdio|http]`.

Defaults to `stdio` — the transport with no port to remember, because that is the one a
client on a desk expects (a Claude Desktop config hands it input on stdin). `http` is
what the deployed instance runs, one process serving both `/mcp` and `/health`.
"""

from __future__ import annotations

import argparse
import asyncio

from .client import UpstreamClient
from .config import Settings
from .server import build_server


async def _serve(transport: str) -> None:
    settings = Settings()
    upstream = UpstreamClient(settings)
    mcp = build_server(settings, upstream)
    try:
        if transport == "stdio":
            await mcp.run_stdio_async()
        else:
            await mcp.run_streamable_http_async()
    finally:
        await upstream.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(prog="market-mcp")
    parser.add_argument("transport", choices=["stdio", "http"], nargs="?", default="stdio")
    args = parser.parse_args()
    asyncio.run(_serve(args.transport))


if __name__ == "__main__":
    main()
