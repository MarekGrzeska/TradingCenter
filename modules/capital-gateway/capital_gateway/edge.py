"""The gateway's side of `tc-entra-auth`: what the door is told, and where it asks. Its own file because the paths
are this module's — `/` is the health probe, `/ws/stream` checks the shared key inside its handler."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI
from tc_entra_auth import EdgeConfig, TokenVerifier

from .config import API_KEY_HEADER, Settings

HEALTH_PATH = "/"
STREAM_PATH = "/ws/stream"


def edge_config(settings: Settings) -> EdgeConfig | None:
    """`None` is not a server: Easy Auth in Azure, or nothing locally, and the door stays as it was."""
    if not settings.server_mode:
        return None
    assert settings.entra_tenant_id is not None  # the settings refuse server mode without it
    return EdgeConfig(
        verifier=TokenVerifier(tenant_id=settings.entra_tenant_id, audiences=settings.audiences),
        service_key=settings.gateway_api_key,
        internal_application_id=settings.internal_caller_application_id,
        key_header=API_KEY_HEADER.lower().encode(),
        exempt_paths=frozenset({HEALTH_PATH}),
        key_paths=frozenset({STREAM_PATH}),
    )


def edge_provider(app: FastAPI) -> Callable[[], EdgeConfig | None]:
    """The config once the lifespan has built it. Before that the state has nothing and the door refuses with a 503,
    because "not read yet" must never be the reading that lets a request in."""

    def provider() -> EdgeConfig | None:
        try:
            return app.state.edge
        except AttributeError:
            raise LookupError("the gateway has not read its settings yet") from None

    return provider
