"""Whose request this is — the one fact every tool here needs before it does anything.

The teams surface filters every statement by the owner it was given, and a team belonging
to somebody else is indistinguishable from one that never existed. So a tool acting on the
process's own identity would write rows the operator cannot see: existing, costing money,
impossible to open.

**What travels changed with the merge, and it is worth reading carefully.** While these
tools stood in their own process, the operator's *bearer token* was carried to them in
`X-Operator-Authorization` and presented to teams as `Authorization`, where the platform
authenticator validated it and put the operator's principal on the request. In one process
there is no authenticator in the middle to validate anything — so what travels is the
**principal itself**, taken off the incoming chat request, which the authenticator in front
of *this* process has already validated. One fewer credential in flight, and the same
answer at the other end.

It is carried in a context variable rather than an argument because the seam it has to
cross is somebody else's: `FastMCP` builds the `Context` a tool receives, and there is no
field on it for this.

**It is never read from a tool argument.** A model writes whatever it finds plausible, and
an identity that can be written is an identity that can be borrowed — from the chat, in one
sentence, by anyone who knows how somebody else's principal reads (specs, "Tożsamość
operatora jest przenoszona, a nie odgadywana"). That holds in every configuration,
including the one below.

**The refusal is bounded, not absolute, and the boundary is "could an identity have
existed".** Behind an authenticator, a missing principal is a broken chain and every tool
refuses — reads as flatly as writes. On a machine where nothing authenticates, no layer
could have issued one at all, and refusing there buys nothing: it takes the whole tool
surface away from a desk. Then the call proceeds carrying **no identity**, and the teams
surface attributes it to the principal it assigns any unauthenticated request — which is
the same one the local terminal gets, so what the chat creates lands on the list the
operator is already looking at. Nothing here chooses anything.

The condition used to have a second half — "or teams is reached at a remote address" —
which lost its subject when the catalogue moved into this process. There is no address.
"""

from __future__ import annotations

from contextvars import ContextVar

from .errors import ToolRefusal

# Set for the duration of one tool call by `local.py`, which is the only writer. A context
# variable rather than a global: several turns run concurrently in this process, and
# `ContextVar` is per task rather than per process.
_operator: ContextVar[str | None] = ContextVar("teams_tools_operator", default=None)

_MISSING = (
    "this call carried no operator identity, so there is nobody to act for. Nothing was "
    "read and nothing was written. The chat that asked for this must be signed in — the "
    "identity is taken from the request being served and never from a tool argument."
)


class carrying:
    """`with carrying(principal):` — one tool call's operator, and nobody else's.

    A context manager rather than a bare `set()` so the token is always reset, including
    when a tool raises: a principal left behind on a task that is reused is the one bug
    this whole file exists to make impossible.
    """

    def __init__(self, principal: str | None) -> None:
        self._principal = principal
        self._token = None

    def __enter__(self) -> None:
        self._token = _operator.set(self._principal)

    def __exit__(self, *exc_info) -> None:
        assert self._token is not None
        _operator.reset(self._token)


def operator_principal(*, optional: bool = False) -> str | None:
    """The operator this one call acts for.

    `ToolRefusal` naming the absence when there is none and one could have existed, which
    is the default and the only behaviour anywhere but a developer's machine. Refuses for
    reads exactly as for writes: without an identity there is no catalogue to read, only
    somebody else's.

    `optional=True` — decided from whether an authenticator stands in front of this
    process, never by a caller's judgement — answers `None` instead, which the client turns
    into a request carrying no principal header at all rather than an empty or invented
    one.
    """
    principal = (_operator.get() or "").strip()
    if principal:
        return principal
    if optional:
        return None
    raise ToolRefusal(_MISSING)


def redacted(principal: str | None) -> str:
    """What a log line may say about an identity: whether there was one, and nothing
    else."""
    return "present" if principal else "absent"
