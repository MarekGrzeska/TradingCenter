"""Who is calling, decided in the process rather than by a platform in front of it."""

from .edge import EDGE_HEADER, EdgeAuth, EdgeConfig, application_in
from .roles import (
    ADMIN_ROLE,
    INTERNAL_ROLE,
    ROLES_HEADER,
    VIEWER_ROLE,
    RolePolicy,
    roles_from_header,
)
from .verifier import InvalidToken, TokenVerifier

__all__ = [
    "ADMIN_ROLE",
    "EDGE_HEADER",
    "INTERNAL_ROLE",
    "ROLES_HEADER",
    "VIEWER_ROLE",
    "EdgeAuth",
    "EdgeConfig",
    "InvalidToken",
    "RolePolicy",
    "TokenVerifier",
    "application_in",
    "roles_from_header",
]
