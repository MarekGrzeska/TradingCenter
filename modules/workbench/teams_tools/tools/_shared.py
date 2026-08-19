"""Helpers every tool submodule needs: the annotations that say which tools change
something, and the one seam that turns a `TeamsClient` outcome into what a tool answers.

The seam is where the operator's identity is required, so no tool can forget it: `_call`
asks `operator.py` who this is before it asks the client for anything, and a call with no
operator behind it never reaches a route ("Brak tożsamości operatora zatrzymuje zapis, nie
podstawia zastępczej") — except on a machine where no layer could have identified one,
which is `operator.py`'s decision to make and not this file's.
"""

from __future__ import annotations

from typing import Any

from mcp.types import ToolAnnotations

from ..client import TeamsClient
from ..errors import ToolRefusal, UpstreamUnavailable
from ..operator import operator_principal

# Applied to every read tool — a structural claim an MCP client can act on without
# reading this module's source (specs/teams-mcp-tools, "Narzędzie zapisujące jest
# oznaczone jako zmieniające stan"). `teams` used to read this same annotation when
# deciding whether a revision could run unattended; that check is gone
# (`manage-schedules-and-drop-the-acknowledgement`), so the annotation is now a claim to
# the client rather than an input to a refusal.
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)

# Applied to every tool that changes the catalogue. `idempotentHint=False` because none
# of them repeat safely: a second `create_team` is a second team, a second `run_team` a
# second bill. `destructiveHint=False` is the honest half — revisions are append-only, so
# nothing here overwrites what was there before.
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False)

# Applied to the two tools that take something away for good. `destructiveHint=True` is
# the whole point of having a third annotation: an MCP client that asks the operator
# before a destructive call has no way to tell `delete_schedule` from `create_team`
# otherwise. `idempotentHint=True` because a second call removes nothing further — the
# row is already gone and the answer is that it is not there.
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
    """One call to `teams` in the operator's name, with both failure shapes turned into
    the one thing a tool may raise.

    `ToolRefusal` and `UpstreamUnavailable` are kept apart all the way up from
    `client.py` and collapse here, into a sentence that still says which of the two it
    was — the model reads the sentence, not the class.
    """
    # Whether an absent identity is allowed is the client's fact, read off the settings it
    # was built from; this seam only carries the answer through. `None` travels on to
    # `client.py` unchanged — nothing here substitutes anything for it. The `context`
    # parameter stays because FastMCP passes one to every tool; it is no longer where the
    # identity comes from.
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
