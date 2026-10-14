"""Settings, and the one thing this module cannot start without: the header `capital-gateway` requires
on every request, loopback included. The token beside it follows the address; the key does not."""

from __future__ import annotations

from pydantic import ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    capital_gateway_url: str = "http://127.0.0.1:8010"
    capital_gateway_api_key: str
    # The gateway's audience, where there is an identity to present it with:
    # `api://tradingcenter-capital-gateway/.default`. Unset is the local shape.
    capital_gateway_scope: str | None = None
    # Chosen against the gateway's ordinary worst case — one slow upstream call plus a prompt confirm
    # poll, about 22s — not its pathological one, where raising this buys precision in a failing gateway.
    capital_gateway_request_timeout_seconds: float = 30.0

    trading_mcp_port: int = 8060
    # Loopback by default; the container overrides it in its Dockerfile.
    trading_mcp_host: str = "127.0.0.1"

    # Whether a platform authenticator stands in front of this module. Off locally, on in Azure.
    require_authenticated_principal: bool = False

    # A server with no platform authenticator (`move-from-azure-to-vps`). This module is never published at the edge,
    # so what reaches it is another service on the internal network, and proves itself with the gateway's key — the one
    # shared secret the system has. Anything carrying the edge marker is refused whatever token it holds.
    server_mode: bool = False
    internal_caller_application_id: str = "tc-internal"

    @model_validator(mode="after")
    def _server_mode_asks_for_an_identity(self) -> Settings:
        if self.server_mode and not self.require_authenticated_principal:
            raise ValueError(
                "SERVER_MODE needs REQUIRE_AUTHENTICATED_PRINCIPAL=true: the door writes the identity the "
                "tools are gated on, and a process that does not ask for it admits a caller with none"
            )
        return self

    @field_validator("capital_gateway_url")
    @classmethod
    def _not_blank_url(cls, value: str, info: ValidationInfo) -> str:
        if not value.strip():
            raise ValueError(f"{str(info.field_name).upper()} is set but empty")
        return value.rstrip("/")

    @field_validator("capital_gateway_api_key")
    @classmethod
    def _not_blank_key(cls, value: str, info: ValidationInfo) -> str:
        # pydantic already rejects a variable that is absent; this catches the one that is present
        # but empty, which is what an unfilled .env actually looks like.
        if not value.strip():
            raise ValueError(f"{str(info.field_name).upper()} is set but empty")
        return value
