"""Settings, and the guards that keep this module off a live account and off the open internet.
Refusing to build the settings leaves nothing running to misuse, which a route check would not."""

from __future__ import annotations

import os

from pydantic import ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEMO_BASE_URL = "https://demo-api-capital.backend-capital.com"
DEMO_STREAM_URL = "wss://api-streaming-capital.backend-capital.com/connect"

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
    return DEMO_ENVIRONMENT if base_url.rstrip("/") == DEMO_BASE_URL else LIVE_ENVIRONMENT


def is_production() -> bool:
    """Whether this process is the deployed one. Read from the environment rather than `Settings`,
    which is not built yet at import time; anything but the exact word is development."""
    return os.getenv(ENV_VAR, "").strip().lower() == PRODUCTION


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    capital_api_key: str
    capital_identifier: str
    capital_password: str
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

    @property
    def audiences(self) -> list[str]:
        return [part.strip() for part in self.entra_audiences.split(",") if part.strip()]

    @field_validator("capital_base_url", "capital_stream_url")
    @classmethod
    def _demo_only(cls, value: str, info: ValidationInfo) -> str:
        # An exact match, not a "looks like demo" test: the live host is the demo one minus a
        # prefix, so any rule loose enough to allow a variant allows the live account.
        expected = DEMO_BASE_URL if info.field_name == "capital_base_url" else DEMO_STREAM_URL
        url = value.rstrip("/")
        if url != expected:
            raise ValueError(
                f"{str(info.field_name).upper()} must be the capital.com demo endpoint "
                f"({expected}); got {value!r}. This module never touches a live account."
            )
        return url
