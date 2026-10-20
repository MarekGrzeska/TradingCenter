"""What a person may reach, decided by the role the token carries — not by the application it was issued to, which a
single-page client shares with every guest of the tenant. The roles come from the verified token only; the header that
hands them to the process's handlers (`GET /me`) is written by `EdgeAuth` after it has dropped whatever the client sent."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

ROLES_HEADER = b"x-tc-roles"

ADMIN_ROLE = "admin"
VIEWER_ROLE = "viewer"
# Written for a request proved by the shared service key, so a service need not pretend to be a person.
INTERNAL_ROLE = "internal"

_SAFE = re.compile(r"^[A-Za-z0-9_.-]+$")


def roles_header_value(roles: Iterable[str]) -> bytes:
    return ",".join(sorted(role for role in roles if _SAFE.match(role))).encode()


def roles_from_header(headers: dict[bytes, bytes]) -> frozenset[str]:
    raw = headers.get(ROLES_HEADER, b"").decode("latin-1")
    return frozenset(part for part in raw.split(",") if part)


def _under(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + "/")


@dataclass(frozen=True)
class RolePolicy:
    """`admin` and `internal` pass everywhere; `viewer` passes only a read (`GET`) under `viewer_read_prefixes`; a person
    with no known role passes nowhere. `open_paths` answer any verified token, so a screen can tell "no access" from
    "down". Compared by equality, never by prefix."""

    viewer_read_prefixes: tuple[str, ...] = ()
    open_paths: frozenset[str] = frozenset({"/me"})
    # A path with one of these segments is never a viewer's, whatever its method: `/mcp` is the tool surface the
    # conversation reaches the account through, and a `GET` on it opens a stream.
    viewer_blocked_segments: frozenset[str] = frozenset({"mcp"})

    def allows(self, roles: frozenset[str], method: str, path: str) -> bool:
        if path in self.open_paths:
            return True
        if roles & {ADMIN_ROLE, INTERNAL_ROLE}:
            return True
        if VIEWER_ROLE in roles:
            if self.viewer_blocked_segments & set(path.split("/")):
                return False
            return method == "GET" and any(_under(path, p) for p in self.viewer_read_prefixes)
        return False
