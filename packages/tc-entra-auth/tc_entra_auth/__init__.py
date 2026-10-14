"""Who is calling, decided in the process rather than by a platform in front of it."""

from .edge import EDGE_HEADER, EdgeAuth, EdgeConfig
from .verifier import InvalidToken, TokenVerifier

__all__ = ["EDGE_HEADER", "EdgeAuth", "EdgeConfig", "InvalidToken", "TokenVerifier"]
