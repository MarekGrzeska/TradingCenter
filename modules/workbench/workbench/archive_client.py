"""The strategy platform's road to the candle archive, when both are packages of one process: the archive's own
application, reached through `httpx.ASGITransport` as this process rather than over the network as a caller.

The platform keeps its REST client (`strategy.archive.Archive`) and the archive keeps its REST contract, route
record and exception handlers — what goes away is the hop: a token for this app's own audience, presented to its
own Easy Auth, to reach itself by public hostname (stage 3a of `one-process-per-security-boundary`). The packages
still do not import each other; this file is the assembly, and it knows both.
"""

from __future__ import annotations

import httpx
from fastapi import FastAPI
from tc_runtime.caller_access import in_process

# Never resolved and never dialled — `ASGITransport` answers whatever the authority says. It exists because
# `httpx` insists on an absolute URL, and `Archive` prefixes every path with it.
ARCHIVE_AUTHORITY = "http://market.in-process"

# Generous, for a backtest reading three hundred bars of three facts at once: the archive's indicator arithmetic
# runs off the event loop, but it still runs. The same number the platform's own HTTP client used.
TIMEOUT_SECONDS = 30.0


def archive_client(market_app: FastAPI) -> httpx.AsyncClient:
    """A client the platform's `Archive` takes, over the archive's application as it is mounted — middleware,
    caller record and exception handlers included, so a refusal or a gateway error reads exactly as it would
    over HTTP. `raise_app_exceptions=False`, so the archive's own 500 is what the platform sees, not a traceback
    crossing from one package into another."""
    transport = httpx.ASGITransport(
        app=in_process(market_app, "the strategy platform"), raise_app_exceptions=False
    )
    return httpx.AsyncClient(
        transport=transport, base_url=ARCHIVE_AUTHORITY, timeout=httpx.Timeout(TIMEOUT_SECONDS)
    )
