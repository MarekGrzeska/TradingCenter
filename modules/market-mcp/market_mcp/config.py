"""Settings, and the one switch that decides how this module reaches `market-data`.

The pattern is the third copy of one already set by `market-data/config.py` and
`agent/config.py`: exactly one setting names the mode, and a configuration that leaves
it ambiguous is rejected at startup rather than guessed at. Here there is only one
setting to check, because there is only one seam — this module has no database of its
own to switch alongside it.

  upstream access   `market_data_scope` set → the archive is off this machine, and a
                     token for that scope is what proves this module to it. Unset →
                     `market_data_url` MUST point at loopback — nothing configured to
                     ask a credential from, so nothing configured to reach beyond this
                     machine (design.md, "Tryb połączenia jest wybrany jednoznacznie,
                     nie zgadnięty").

Refusing to build the settings leaves nothing running to misuse.
"""

from __future__ import annotations

from urllib.parse import urlparse

from pydantic import ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- market-data, this module's only upstream ---
    market_data_url: str = "http://127.0.0.1:8020"
    # api://<market-data-app-id>/.default — the scope a managed identity requests a
    # token for. Set only when `market_data_url` is not loopback.
    market_data_scope: str | None = None
    market_data_request_timeout_seconds: float = 10.0

    # --- this module's own HTTP surface, for the streamable-http transport ---
    mcp_http_port: int = 8040

    @field_validator("market_data_url")
    @classmethod
    def _not_blank(cls, value: str, info: ValidationInfo) -> str:
        if not value.strip():
            raise ValueError(f"{str(info.field_name).upper()} is set but empty")
        return value.rstrip("/")

    @field_validator("market_data_scope")
    @classmethod
    def _blank_scope_means_unset(cls, value: str | None) -> str | None:
        # MARKET_DATA_SCOPE= left in a .env is the same intent as the line being
        # absent — local mode — not a scope named "".
        if value is None or not value.strip():
            return None
        return value.strip()

    @model_validator(mode="after")
    def _upstream_mode_is_coherent(self) -> Settings:
        host = (urlparse(self.market_data_url).hostname or "").lower()
        is_loopback = host == "localhost" or host.startswith("127.") or host == "::1"

        if self.market_data_scope is not None:
            if is_loopback:
                raise ValueError(
                    f"MARKET_DATA_SCOPE is set but MARKET_DATA_URL points at loopback "
                    f"({self.market_data_url!r}) — a scope belongs to a remote archive; "
                    "unset MARKET_DATA_SCOPE for local development, or point the URL at "
                    "the remote instance it names a token for."
                )
            return self

        if not is_loopback:
            raise ValueError(
                f"MARKET_DATA_URL points at {host!r} with no MARKET_DATA_SCOPE set. "
                "Without a scope this module only connects to an archive on this "
                "machine's loopback — a remote archive needs MARKET_DATA_SCOPE and the "
                "managed identity it is requested for."
            )
        return self
