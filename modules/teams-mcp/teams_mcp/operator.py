"""Whose request this is — the one fact every tool here needs before it does anything.

`teams` filters every statement by the owner it was given, and a team belonging to
somebody else is indistinguishable from one that never existed. So a tool acting on the
module's own identity would write rows the operator cannot see: existing, costing money,
impossible to open (design.md, D2).

The operator's token therefore travels with the call. It cannot ride in `Authorization`,
because that header carries `agent`'s own identity to the authenticator standing in front
of *this* module — two different questions, two different headers:

    Authorization:            who is calling teams-mcp        (agent, a managed identity)
    X-Operator-Authorization: in whose name they are calling  (the operator's own token)

The second is read here and presented as `Authorization` to `teams`, where the platform
authenticator validates it and puts the operator's principal on the request — exactly the
sequence the terminal already produces when the operator clicks something.

**It is never read from a tool argument.** A model writes whatever it finds plausible, and
an identity that can be written is an identity that can be borrowed — from the chat, in one
sentence, by anyone who knows how somebody else's principal reads
(specs/teams-mcp-authorship, "Tożsamość operatora jest przenoszona, a nie odgadywana").

**It is never logged, stored or handed back to the model.** `redacted()` exists so that a
diagnostic can say whether a token was there without saying what it was.
"""

from __future__ import annotations

from typing import Any

from .errors import ToolRefusal

OPERATOR_TOKEN_HEADER = "x-operator-authorization"

_MISSING = (
    "this call carried no operator identity, so there is nobody to act for. Nothing was "
    "read and nothing was written. The chat that asked for this must be signed in, and "
    f"its token reaches here in the {OPERATOR_TOKEN_HEADER} header — it is never taken "
    "from a tool argument."
)


def operator_token(context: Any) -> str:
    """The operator's own credential for this one call, or `ToolRefusal` naming its
    absence. Refuses for reads exactly as for writes: without an identity there is no
    catalogue to read, only somebody else's (specs/teams-mcp-authorship)."""
    request = getattr(getattr(context, "request_context", None), "request", None)
    headers = getattr(request, "headers", None)
    if headers is None:
        raise ToolRefusal(_MISSING)

    value = (headers.get(OPERATOR_TOKEN_HEADER) or "").strip()
    if not value:
        raise ToolRefusal(_MISSING)
    return value


def redacted(token: str | None) -> str:
    """What a log line may say about a token: whether there was one, and nothing else."""
    return "present" if token else "absent"
