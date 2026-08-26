"""Settings, and the one thing this module cannot start without: the header `capital-gateway` requires
on every request, loopback included. The token beside it follows the address; the key does not."""

from __future__ import annotations

from pydantic import ValidationInfo, field_validator
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
