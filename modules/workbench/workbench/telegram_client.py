"""The door to Telegram as the post archive and the YouTube archive reach it, when all of them are packages of one
process: the gateway's own application through `httpx.ASGITransport`, as this process.

Both callers keep their REST client and the gateway keeps its contract, route record and refusals; what goes away is
an address, a scope and a token for another App Service's audience.
"""

from __future__ import annotations

import httpx
from fastapi import FastAPI
from tc_runtime.caller_access import in_process

# Never resolved and never dialled — `ASGITransport` answers whatever the authority says.
TELEGRAM_AUTHORITY = "http://telegram.in-process"

# Connect is nothing here; read is generous because the request is a message on its way to Telegram, which is the
# same ceiling both callers held over the network.
TIMEOUT = httpx.Timeout(connect=5.0, read=35.0, write=10.0, pool=5.0)


def telegram_client(telegram_app: FastAPI, caller: str) -> httpx.AsyncClient:
    """A client for `POST /messages`, over the gateway as it is mounted — middleware and caller record included,
    so a refusal reads exactly as it did over HTTP. `caller` is who the gateway's log says asked."""
    transport = httpx.ASGITransport(
        app=in_process(telegram_app, caller), raise_app_exceptions=False
    )
    return httpx.AsyncClient(transport=transport, base_url=TELEGRAM_AUTHORITY, timeout=TIMEOUT)


def package_client(package_app: FastAPI, caller: str, authority: str) -> httpx.AsyncClient:
    """The same for any other package's REST contract, in this process: what one package reads of another's without going
    through the door. `authority` is never dialled; it only has to be a URL."""
    transport = httpx.ASGITransport(app=in_process(package_app, caller), raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url=authority, timeout=TIMEOUT)

