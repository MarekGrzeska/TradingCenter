"""The trace a write leaves here (`trading-mcp-transport`): one line before it is sent and one with its outcome. The
conversation keeps its own in a database; a caller from outside bypasses the conversation, so this is the only one the
system has of it. Never a token or a key — only what the door wrote after checking them."""

from __future__ import annotations

import json
import logging
from typing import Any

from tc_entra_auth import application_in
from tc_mcp_kit.tool_call import request_header

log = logging.getLogger("trading_mcp.trace")

UNKNOWN = "unknown"


def caller() -> tuple[str, str]:
    """The application and the person of the call being served, as `EdgeAuth` wrote them."""
    application = application_in(request_header("x-ms-client-principal"))
    return application or UNKNOWN, request_header("x-ms-client-principal-id") or UNKNOWN


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
