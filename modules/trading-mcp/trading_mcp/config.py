"""Settings, and the one thing this module cannot start without: the header
`capital-gateway` requires on every request, loopback included.

`capital-gateway` checks a static shared key (`X-Gateway-Key`, `RequireGatewayKey` in its
own `app.py`) on every caller regardless of where it is running. There is no loopback
exemption to switch on, so the key is required at every address, full stop
(specs/trading-mcp-upstream-access, "Poświadczenie do gatewaya jest wymagane niezależnie
od adresu").

What *does* follow the address is the second credential. Where this module has an identity
in the directory it also presents a token for the gateway's audience
(`CAPITAL_GATEWAY_SCOPE`), because the gateway's own door validates tokens rather than
trusting a key two modules share. Absent, there is nothing to ask for a token and the key
is the whole credential — the local shape, and not a degraded one.

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
    # The gateway's audience, where there is an identity to present it with:
    # `api://tradingcenter-capital-gateway/.default`. Unset is the local shape.
    capital_gateway_scope: str | None = None
    # Chosen against the gateway's *ordinary* worst case, not its pathological one, and
    # the difference is worth stating because the arithmetic here was wrong once.
    #
    # Ordinary: one slow upstream call (`capital_gateway/client.py`, 20s) plus the
    # confirm-poll loop answering promptly (`adapter.py`, 5 attempts, 0.4s apart) ≈ 22s.
    # 30 covers that with room.
    #
    # Pathological: every one of those 5 polls *itself* times out at 20s, and the
    # gateway takes ~122s to answer at all. Nothing here waits that long on purpose. A
    # gateway in that state is a gateway in trouble, and this module's answer —
    # "access failure, the effect on the account is unknown, go read positions, do not
    # repeat this call" — is the true one; the order it stopped waiting for may well
    # have filled, and saying so is exactly what `outcome` unknown means downstream
    # (`teams`' trade trace keeps that row as `sent`).
    #
    # So: raising this buys precision in a case where the gateway is already failing,
    # and costs an agent — and the operator watching it — two minutes of a run's
    # 15-minute ceiling on every such call. `teams` sets its own ceiling just past this
    # one (35s) so the layering stays in this order.
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
