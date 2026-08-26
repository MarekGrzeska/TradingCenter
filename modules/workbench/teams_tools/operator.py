"""Whose request this is — the fact every tool needs first, because the teams surface filters by owner. What travels is
the principal itself, in a context variable rather than an argument: an identity that can be written can be borrowed."""

from __future__ import annotations

from contextvars import ContextVar

from .errors import ToolRefusal

# Set for the duration of one tool call by `local.py`, which is the only writer. A context variable rather
# than a global: several turns run concurrently, and `ContextVar` is per task rather than per process.
_operator: ContextVar[str | None] = ContextVar("teams_tools_operator", default=None)

_MISSING = (
    "this call carried no operator identity, so there is nobody to act for. Nothing was "
    "read and nothing was written. The chat that asked for this must be signed in — the "
    "identity is taken from the request being served and never from a tool argument."
)


class carrying:
    """`with carrying(principal):` — one tool call's operator, and nobody else's. A context manager so the
    token is always reset, including when a tool raises."""

    def __init__(self, principal: str | None) -> None:
        self._principal = principal
        self._token = None

    def __enter__(self) -> None:
        self._token = _operator.set(self._principal)

    def __exit__(self, *exc_info) -> None:
        assert self._token is not None
        _operator.reset(self._token)


def operator_principal(*, optional: bool = False) -> str | None:
    """The operator this one call acts for, refusing for reads exactly as for writes: without an identity there is no
    catalogue to read, only somebody else's. `optional=True` answers `None`, which becomes a request with no principal."""
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
