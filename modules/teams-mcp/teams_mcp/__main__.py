"""Entry point: `python -m teams_mcp`.

One transport, one mode — see `server.py` for why there is no `stdio` to choose between.

Nothing is checked against `teams` before the port opens, and that is deliberate: unlike
`trading-mcp`, whose demo-account guard has to hold before anything can be called, this
module has no fact about `teams` worth refusing to start over. A `teams` that is down is a
tool call that reports it, not a process that will not run — the same shape `market-mcp`
already has toward the archive.
"""

from __future__ import annotations

import asyncio

import uvicorn

from .client import TeamsClient
from .config import Settings
from .server import build_http_app


async def _serve() -> None:
    settings = Settings()  # type: ignore[call-arg]
    teams = TeamsClient(settings)
    try:
        app = build_http_app(settings, teams)
        config = uvicorn.Config(app, host=settings.teams_mcp_host, port=settings.teams_mcp_port)
        await uvicorn.Server(config).serve()
    finally:
        await teams.aclose()


def main() -> None:
    asyncio.run(_serve())


if __name__ == "__main__":
    main()
