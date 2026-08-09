"""Settings, and the guards that keep this module off a live account and off the
open internet.

The guards run here rather than on the trading routes on purpose: a runtime check
would still leave an authenticated live session sitting in the process, readable by
every other route. Refusing to build the settings leaves nothing running to misuse.
The same reasoning covers the caller credential — a module that starts without one
is an open trading endpoint, and nothing about it looks wrong until it is used.
"""

from __future__ import annotations

import os

from pydantic import ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEMO_BASE_URL = "https://demo-api-capital.backend-capital.com"
DEMO_STREAM_URL = "wss://api-streaming-capital.backend-capital.com/connect"

# The header a caller presents. Named for the module rather than for the scheme,
# because the value is this gateway's own key and has nothing to do with capital.com.
API_KEY_HEADER = "X-Gateway-Key"

ENV_VAR = "GATEWAY_ENV"
PRODUCTION = "production"


def is_production() -> bool:
    """Whether this process is the deployed one.

    Read from the environment directly rather than from `Settings`, because the
    answer is needed when the FastAPI application object is constructed at import
    time — before a `.env` has been loaded and before credentials are required.
    Anything other than the exact word is development: a typo must not silently
    publish the schema of a trading API.
    """
    return os.getenv(ENV_VAR, "").strip().lower() == PRODUCTION


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    capital_api_key: str
    capital_identifier: str
    capital_password: str
    capital_base_url: str = DEMO_BASE_URL
    capital_stream_url: str = DEMO_STREAM_URL
    gateway_api_key: str

    @field_validator("capital_api_key", "capital_identifier", "capital_password", "gateway_api_key")
    @classmethod
    def _not_blank(cls, value: str, info: ValidationInfo) -> str:
        # pydantic already rejects a variable that is absent; this catches the one that
        # is present but empty, which is what an unfilled .env actually looks like.
        if not value.strip():
            raise ValueError(f"{str(info.field_name).upper()} is set but empty")
        return value

    @field_validator("capital_base_url", "capital_stream_url")
    @classmethod
    def _demo_only(cls, value: str, info: ValidationInfo) -> str:
        # An exact match, not a "looks like demo" test. The live REST host is the demo
        # one minus a prefix, so any rule loose enough to allow a variant is loose
        # enough to allow the live account.
        expected = DEMO_BASE_URL if info.field_name == "capital_base_url" else DEMO_STREAM_URL
        url = value.rstrip("/")
        if url != expected:
            raise ValueError(
                f"{str(info.field_name).upper()} must be the capital.com demo endpoint "
                f"({expected}); got {value!r}. This module never touches a live account."
            )
        return url
