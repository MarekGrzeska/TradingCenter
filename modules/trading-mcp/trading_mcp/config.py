"""Settings, and the one thing this module cannot start without: the header
`capital-gateway` requires on every request, loopback included.

Unlike `market-mcp`'s upstream — `market-data`, gated by Easy Auth and a managed-identity
scope that only applies once the archive is off this machine — `capital-gateway` checks a
static shared key (`X-Gateway-Key`, `RequireGatewayKey` in its own `app.py`) on every
caller regardless of where it is running. There is no loopback exemption to switch on, so
there is no mode to select: the key is required, full stop
(specs/trading-mcp-upstream-access, "Poświadczenie do gatewaya jest wymagane niezależnie
od adresu").

Refusing to build the settings leaves nothing running to misuse — the same reasoning
`capital_gateway/config.py` itself uses for its own credential.
"""

from __future__ import annotations

from pydantic import ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- capital-gateway, this module's only upstream ---
    capital_gateway_url: str = "http://127.0.0.1:8010"
    capital_gateway_api_key: str
    # The gateway's own worst case is its confirm-poll loop (adapter.py, 5 attempts *
    # 0.4s) layered on its own 20s upstream timeout (client.py) — this has to outlast
    # both, or a slow-but-real settlement reads as this module's own failure.
    capital_gateway_request_timeout_seconds: float = 30.0

    # --- this module's own HTTP surface, for the streamable-http transport ---
    trading_mcp_port: int = 8060
    # Loopback by default; the container overrides it (`Dockerfile`, ENV) — see
    # `market_mcp/config.py`'s field of the same shape for why this is spelled out
    # here rather than left to uvicorn's own default.
    trading_mcp_host: str = "127.0.0.1"

    # Whether a platform authenticator (Easy Auth) stands in front of this module — see
    # `market_mcp/config.py`'s field of the same name. Off locally, on in Azure
    # (`infra/app-service.tf`).
    require_authenticated_principal: bool = False

    @field_validator("capital_gateway_url")
    @classmethod
    def _not_blank_url(cls, value: str, info: ValidationInfo) -> str:
        if not value.strip():
            raise ValueError(f"{str(info.field_name).upper()} is set but empty")
        return value.rstrip("/")

    @field_validator("capital_gateway_api_key")
    @classmethod
    def _not_blank_key(cls, value: str, info: ValidationInfo) -> str:
        # pydantic already rejects a variable that is absent; this catches the one
        # that is present but empty, which is what an unfilled .env actually looks
        # like (specs/trading-mcp-upstream-access, "Bez poświadczenia do gatewaya
        # moduł nie wstaje").
        if not value.strip():
            raise ValueError(f"{str(info.field_name).upper()} is set but empty")
        return value
