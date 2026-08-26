"""Helpers every tool submodule needs: the annotations that say which tools change something, and the one
seam that turns a `TeamsClient` outcome into what a tool answers.

The seam is where the operator's identity is required, so no tool can forget it — except on a machine where
no layer could have identified one, which is `operator.py`'s decision to make and not this file's."""

from __future__ import annotations

from typing import Any

from mcp.types import ToolAnnotations

from ..client import TeamsClient
from ..errors import ToolRefusal, UpstreamUnavailable
from ..operator import operator_principal

# Applied to every read tool — a structural claim an MCP client can act on without reading this source.
# `teams` used to read it when deciding whether a revision could run unattended; that check is gone.
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)

# Applied to every tool that changes the catalogue. `idempotentHint=False` because none repeat safely, and
# `destructiveHint=False` is the honest half: revisions are append-only.
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False)

# Applied to the two tools that take something away for good. `destructiveHint=True` is the whole point: a
# client that asks the operator first has no way to tell `delete_schedule` from `create_team` otherwise.
DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True)


async def _call(
    teams: TeamsClient,
    context: Any,
    method: str,
    path: str,
    *,
    params: dict | None = None,
    json: dict | None = None,
) -> Any:
    """One call to `teams` in the operator's name, with both failure shapes turned into the one thing a tool
    may raise. They are kept apart all the way up and collapse here, into a sentence saying which it was."""
    # Whether an absent identity is allowed is the client's fact, read off the settings it was built from.
    # The `context` parameter stays because FastMCP passes one; it is no longer where the identity comes from.
    token = operator_principal(optional=teams.operator_identity_optional)
    try:
        if method == "GET":
            return await teams.get(path, token=token, params=params)
        if method == "POST":
            return await teams.post(path, token=token, json=json)
        if method == "PUT":
            return await teams.put(path, token=token, json=json)
        if method == "DELETE":
            return await teams.delete(path, token=token)
        raise ValueError(f"unsupported method {method}")  # pragma: no cover - programming error
    except UpstreamUnavailable as err:
        raise ToolRefusal(f"access failure: {err}") from err


def summarised(text: str | None, limit: int = 2000) -> str | None:
    """An agent's output as a trace reader needs it. Long enough to reason about, short
    enough that reading six of them does not fill the turn that was meant to fix them."""
    if text is None:
        return None
    if len(text) <= limit:
        return text
    return text[:limit] + f"… [{len(text) - limit} more characters, read the run in the terminal]"
