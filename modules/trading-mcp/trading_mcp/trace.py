"""The trace a write leaves here (`trading-mcp-transport`): one line before it is sent and one with its outcome. The
conversation keeps its own in a database; a caller from outside bypasses the conversation, so this is the only one the
system has of it. Never a token or a key — only what the door wrote after checking them."""

from __future__ import annotations

import base64
import binascii
import json
import logging
from typing import Any

from mcp.server.lowlevel.server import request_ctx

log = logging.getLogger("trading_mcp.trace")

UNKNOWN = "unknown"


def caller() -> tuple[str, str]:
    """The application and the person of the call being served, as `EdgeAuth` wrote them. Read from the request of this
    tool call rather than from a context variable set around the HTTP request: in stateful streamable-http the tool runs
    in the session's task, which never sees one."""
    try:
        request = request_ctx.get().request
    except LookupError:
        return UNKNOWN, UNKNOWN
    headers = getattr(request, "headers", None)
    if headers is None:
        return UNKNOWN, UNKNOWN
    return _application(headers.get("x-ms-client-principal")), headers.get("x-ms-client-principal-id") or UNKNOWN


def _application(blob: str | None) -> str:
    if not blob:
        return UNKNOWN
    try:
        document = json.loads(base64.b64decode(blob + "=" * (-len(blob) % 4)))
    except (ValueError, binascii.Error):
        return UNKNOWN
    for claim in document.get("claims") or []:
        if isinstance(claim, dict) and claim.get("typ") in ("azp", "appid") and claim.get("val"):
            return str(claim["val"])
    return UNKNOWN


def sending(method: str, path: str, body: dict[str, Any] | None) -> tuple[str, str]:
    application, person = caller()
    log.info(
        "account write sending: %s %s body=%s application=%s person=%s",
        method,
        path,
        json.dumps(body, sort_keys=True) if body is not None else "-",
        application,
        person,
    )
    return application, person


def outcome(method: str, path: str, result: str, who: tuple[str, str]) -> None:
    log.info("account write outcome: %s %s %s application=%s person=%s", method, path, result, *who)
