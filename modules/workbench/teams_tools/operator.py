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
That holds in every configuration, including the one below.

**The refusal is bounded, not absolute, and the boundary is "could an identity have
existed".** Behind an authenticator, or against a remote `teams`, a missing token is a
broken chain and every tool refuses — reads as flatly as writes. On a machine where
neither holds, no layer could have issued a token at all, and refusing there buys nothing:
it takes the whole tool surface away from a desk (`config.py`,
`Settings.operator_identity_optional`). Then the call proceeds carrying **no identity**,
and `teams` attributes it to the principal it assigns any unauthenticated request — which
is the same one the local terminal gets, so what the chat creates lands on the list the
operator is already looking at. This module still chooses nothing and sends nothing.

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


def operator_token(context: Any, *, optional: bool = False) -> str | None:
    """The operator's own credential for this one call.

    `ToolRefusal` naming the absence when there is none and one could have existed, which
    is the default and the only behaviour anywhere but a developer's machine. Refuses for
    reads exactly as for writes: without an identity there is no catalogue to read, only
    somebody else's (specs/teams-mcp-authorship).

    `optional=True` — passed only from `Settings.operator_identity_optional`, never decided
    here and never by a caller's judgement — answers `None` instead, which the client turns
    into a request with no `Authorization` at all rather than an empty or invented one.
    """
    try:
        # `Context.request_context` raises rather than answering `None` when a tool runs
        # outside a request, so this cannot be a `getattr` with a default.
        request = context.request_context.request
    except (ValueError, AttributeError):
        return _absent(optional)

    headers = getattr(request, "headers", None)
    if headers is None:
        return _absent(optional)

    value = (headers.get(OPERATOR_TOKEN_HEADER) or "").strip()
    if not value:
        return _absent(optional)
    return value


def _absent(optional: bool) -> None:
    """One place decides what an absence means, so the three ways of arriving at one — no
    request, no headers, a blank header — cannot drift apart."""
    if optional:
        return
    raise ToolRefusal(_MISSING)


def redacted(token: str | None) -> str:
    """What a log line may say about a token: whether there was one, and nothing else."""
    return "present" if token else "absent"
