"""Settings, and the guards that keep this module on the account it was deployed for and off the open internet.
Refusing to build the settings leaves nothing running to misuse, which a route check would not."""

from __future__ import annotations

import os
from decimal import Decimal
from typing import Literal

from pydantic import ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEMO_BASE_URL = "https://demo-api-capital.backend-capital.com"
DEMO_STREAM_URL = "wss://api-streaming-capital.backend-capital.com/connect"
LIVE_BASE_URL = "https://api-capital.backend-capital.com"

# The header a caller presents. Named for the module rather than for the scheme,
# because the value is this gateway's own key and has nothing to do with capital.com.
API_KEY_HEADER = "X-Gateway-Key"

ENV_VAR = "GATEWAY_ENV"
PRODUCTION = "production"

DEMO_ENVIRONMENT = "demo"
LIVE_ENVIRONMENT = "live"


def environment_of(base_url: str) -> str:
    """Which capital.com environment a base URL belongs to. It exists so the answer is *read*
    rather than asserted: `trading-mcp` asks `/capabilities` before it opens a port."""
    url = base_url.rstrip("/")
    if url == DEMO_BASE_URL:
        return DEMO_ENVIRONMENT
    return LIVE_ENVIRONMENT if url == LIVE_BASE_URL else "unknown"


def is_production() -> bool:
    """Whether this process is the deployed one. Read from the environment rather than `Settings`,
    which is not built yet at import time; anything but the exact word is development."""
    return os.getenv(ENV_VAR, "").strip().lower() == PRODUCTION


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    capital_api_key: str
    capital_identifier: str
    capital_password: str
    # Declared before the URLs on purpose: their validator reads it from the fields already validated.
    capital_environment: Literal["demo", "live"] = DEMO_ENVIRONMENT
    capital_base_url: str = DEMO_BASE_URL
    capital_stream_url: str = DEMO_STREAM_URL
    gateway_api_key: str
    # Who reaches what in production, by the application a platform-validated token names. Modules reach
    # everything, browsers the account; the shared key opens no HTTP route there — it is the credential of
    # `/ws/stream` and of local work. Empty everywhere but production, and empty means nobody.
    module_caller_application_ids: list[str] = []
    browser_caller_application_ids: list[str] = []

    # A server with no platform authenticator in front (`move-from-azure-to-vps`): the process checks the Entra
    # token itself for what came through the edge proxy, and the shared key for what came from another service.
    # Off everywhere else. Audiences are comma-separated, the way an App Service setting is easiest to write.
    server_mode: bool = False
    entra_tenant_id: str | None = None
    entra_audiences: str = ""
    # What a caller proving itself with the key is called; always a module caller, with nothing to add to the list.
    internal_caller_application_id: str = "tc-internal"

    # The live account's own rules (`live-account-trading`): the one account this process stands on, and per symbol the
    # largest size one order may carry — the keys are the instruments it may trade at all. Read only when live.
    live_account_id: str | None = None
    live_order_limits: dict[str, Decimal] = {}

    @field_validator("capital_api_key", "capital_identifier", "capital_password", "gateway_api_key")
    @classmethod
    def _not_blank(cls, value: str, info: ValidationInfo) -> str:
        # pydantic already rejects a variable that is absent; this catches the one that
        # is present but empty, which is what an unfilled .env actually looks like.
        if not value.strip():
            raise ValueError(f"{str(info.field_name).upper()} is set but empty")
        return value

    @model_validator(mode="after")
    def _server_mode_is_coherent(self) -> Settings:
        if not self.server_mode:
            return self
        if not is_production():
            # Without it the key opens every HTTP route, which is the one thing a server must not offer.
            raise ValueError(f"SERVER_MODE needs {ENV_VAR}={PRODUCTION}: the key opens HTTP routes otherwise")
        if not (self.entra_tenant_id or "").strip() or not self.audiences:
            raise ValueError(
                "SERVER_MODE needs ENTRA_TENANT_ID and ENTRA_AUDIENCES — without them no token could be checked, "
                "and a browser would have no way in"
            )
        if self.internal_caller_application_id not in self.module_caller_application_ids:
            self.module_caller_application_ids = [
                *self.module_caller_application_ids,
                self.internal_caller_application_id,
            ]
        return self

    @model_validator(mode="after")
    def _live_is_bounded(self) -> Settings:
        if self.capital_environment != LIVE_ENVIRONMENT:
            return self
        if not (is_production() and self.server_mode):
            # The dev stack and the tests never hold real money; the first live order happens on the server.
            raise ValueError(
                f"CAPITAL_ENVIRONMENT=live runs only on the server ({ENV_VAR}={PRODUCTION} and SERVER_MODE=true)"
            )
        if self.capital_base_url != LIVE_BASE_URL:
            # A default is not validated by the field validator, so an unset URL would otherwise stay the demo host.
            raise ValueError(f"CAPITAL_ENVIRONMENT=live needs CAPITAL_BASE_URL={LIVE_BASE_URL}")
        if not (self.live_account_id or "").strip():
            raise ValueError("CAPITAL_ENVIRONMENT=live needs LIVE_ACCOUNT_ID: the one account this process trades")
        if not self.live_order_limits:
            raise ValueError(
                'CAPITAL_ENVIRONMENT=live needs LIVE_ORDER_LIMITS, e.g. {"US100": "0.5"}: no limits, no live trading'
            )
        bad = sorted(symbol for symbol, size in self.live_order_limits.items() if not size > 0)
        if bad:
            raise ValueError(f"LIVE_ORDER_LIMITS needs a size above zero for: {', '.join(bad)}")
        return self

    @property
    def audiences(self) -> list[str]:
        return [part.strip() for part in self.entra_audiences.split(",") if part.strip()]

    @field_validator("capital_base_url", "capital_stream_url")
    @classmethod
    def _demo_only(cls, value: str, info: ValidationInfo) -> str:
        # An exact match, not a "looks like demo" test: the live host is the demo one minus a
        # prefix, so any rule loose enough to allow a variant allows the live account. The live host
        # is accepted only when the environment says live in so many words — never inferred from a URL.
        live = info.data.get("capital_environment") == LIVE_ENVIRONMENT
        if info.field_name == "capital_stream_url":
            expected = DEMO_STREAM_URL  # the one stream address the provider documents, for both
        else:
            expected = LIVE_BASE_URL if live else DEMO_BASE_URL
        url = value.rstrip("/")
        if url != expected:
            if live:
                raise ValueError(
                    f"{str(info.field_name).upper()} must be the capital.com live endpoint ({expected}) "
                    f"when CAPITAL_ENVIRONMENT=live; got {value!r}"
                )
            raise ValueError(
                f"{str(info.field_name).upper()} must be the capital.com demo endpoint "
                f"({expected}); got {value!r}. Without CAPITAL_ENVIRONMENT=live this module never "
                "touches a live account."
            )
        return url
