"""The workbench's side of `tc-entra-auth`: which paths need no proof, and where the door looks for its config. Paths
are as the edge proxy sees them — under the package prefixes — and are exactly what Easy Auth used to exclude."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI
from tc_entra_auth import EdgeConfig, TokenVerifier

from .config import Settings

# The deploy probe; the archive's `/ping`, which answers a constant; and its one WebSocket, which cannot carry a header
# and is defended by a single-use ticket (`market_data/tickets.py`). Asserted by equality, never by prefix.
EXEMPT_PATHS = frozenset({"/health", "/market/ping", "/market/ws/candles"})


def edge_config(settings: Settings) -> EdgeConfig | None:
    """`None` is not a server: Easy Auth in Azure, or nothing locally, and the door stays as it was."""
    if not settings.server_mode:
        return None
    assert settings.entra_tenant_id is not None  # the settings refuse server mode without it
    return EdgeConfig(
        verifier=TokenVerifier(tenant_id=settings.entra_tenant_id, audiences=settings.audiences),
        # No service calls the workbench over the network, so no key opens it.
        service_key=None,
        exempt_paths=EXEMPT_PATHS,
    )


def edge_provider(app: FastAPI) -> Callable[[], EdgeConfig | None]:
    """The config once the lifespan has built it; before that the door refuses with a 503."""

    def provider() -> EdgeConfig | None:
        try:
            return app.state.edge
        except AttributeError:
            raise LookupError("the workbench has not read its settings yet") from None

    return provider
