"""Settings, and the four ways this module refuses to start rather than misbehave. Three are the database
rule every schema here carries; the fourth is its own — the archive is its only upstream."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from pydantic import ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# `prefer`/`allow` still let the client fall back to plaintext if the server offers no TLS, and the spec
# requires the connection MUST be encrypted, not merely offered it.
_TLS_REQUIRING_SSLMODES = {"require", "verify-ca", "verify-full"}


def _identifiers(raw: str) -> frozenset[str]:
    """A comma-separated setting as a set, with blanks and stray spaces dropped."""
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # The REST contract, not the tool surface at `/mcp`: that surface is narrowed for a model, which is
    # right for an agent and too tight for a loop.
    market_data_url: str = "http://localhost:8020"
    # The archive's own audience, when this module has an identity to present. Absent is a working
    # configuration and the local one; set, every request carries a bearer token.
    market_data_scope: str | None = None
    market_data_request_timeout_seconds: float = 30.0

    # `database_user` selects between the two connection modes and is the only switch: set means
    # identity mode over TLS with no credential in the URL, unset means the URL as given, on loopback.
    database_url: str
    database_user: str | None = None

    # Identity mode only, and unset even there when running in Azure — the App Service's
    # system-assigned managed identity needs no configuration.
    azure_client_id: str | None = None
    azure_client_secret: str | None = None
    azure_tenant_id: str | None = None

    # Five minutes. This module's tables are small and its migrations are short; the
    # twenty-five market-data allows itself is sized for an index over the candle table.
    migration_lock_wait_seconds: float = 300.0

    # How often the loop wakes to ask whether a new bar has closed — not the resolution it decides on.
    # Waking more often than the bar closes costs one cheap query that finds nothing new.
    evaluation_interval_seconds: int = 60

    # Whether a platform authenticator stands in front. The module MUST NOT assume the layer in front is
    # doing its job: one wrong line in Terraform would leave both surfaces open.
    require_authenticated_principal: bool = False

    # Easy Auth authorizes an application, not a route. These two lists are what it cannot say: who is
    # here for the read-only `/mcp` surface, and who for the REST contract.
    tool_caller_application_ids: str = ""
    rest_caller_application_ids: str = ""

    @property
    def tool_caller_ids(self) -> frozenset[str]:
        return _identifiers(self.tool_caller_application_ids)

    @property
    def rest_caller_ids(self) -> frozenset[str]:
        return _identifiers(self.rest_caller_application_ids)

    @field_validator("market_data_url")
    @classmethod
    def _a_usable_upstream(cls, value: str, info: ValidationInfo) -> str:
        parsed = urlparse(value)
        if not parsed.hostname:
            raise ValueError(f"{str(info.field_name).upper()} is not a usable URL: {value!r}")
        if parsed.scheme not in {"http", "https"}:
            raise ValueError(
                f"{str(info.field_name).upper()} must be http or https, not "
                f"{parsed.scheme!r} — this module reaches the archive over its REST "
                "contract."
            )
        return value.rstrip("/")

    @field_validator("database_url")
    @classmethod
    def _not_blank(cls, value: str, info: ValidationInfo) -> str:
        # pydantic already rejects a variable that is absent; this catches the one that is
        # present but empty, which is what an unfilled .env actually looks like.
        if not value.strip():
            raise ValueError(f"{str(info.field_name).upper()} is set but empty")
        return value.strip()

    @field_validator("database_user")
    @classmethod
    def _blank_means_unset(cls, value: str | None) -> str | None:
        # `DATABASE_USER=` left in a .env is the same intent as the line being absent —
        # local mode — not a role named "".
        if value is None or not value.strip():
            return None
        return value.strip()

    @field_validator("evaluation_interval_seconds")
    @classmethod
    def _positive(cls, value: int, info: ValidationInfo) -> int:
        if value < 1:
            raise ValueError(f"{str(info.field_name).upper()} must be at least 1; got {value}")
        return value

    @model_validator(mode="after")
    def _connection_mode_is_coherent(self) -> Settings:
        """The two connection modes, each with its own failure to refuse. Identity mode is off this
        machine, so TLS and no credential; local mode is the URL as given, and must be loopback."""
        parsed = urlparse(self.database_url)
        if self.database_user is not None:
            sslmode = parse_qs(parsed.query).get("sslmode", [None])[0]
            if sslmode not in _TLS_REQUIRING_SSLMODES:
                raise ValueError(
                    f"DATABASE_URL does not require TLS (sslmode={sslmode!r}). With "
                    "DATABASE_USER set this module connects to a database off this "
                    "machine, so the connection MUST be encrypted — set sslmode=require "
                    "(or verify-ca/verify-full)."
                )
            if parsed.username or parsed.password:
                raise ValueError(
                    "DATABASE_URL carries a username or password. With DATABASE_USER set "
                    "this module authenticates with an Entra token fetched at connection "
                    "time — a credential embedded in the URL is not read and should not "
                    "be there."
                )
            return self

        host = (parsed.hostname or "").lower()
        if not (host == "localhost" or host.startswith("127.") or host == "::1"):
            raise ValueError(
                f"DATABASE_URL points at {host!r} with no DATABASE_USER set. Without an "
                "identity this module only connects to a database on this machine's "
                "loopback — a remote database (production included) needs DATABASE_USER "
                "and an Entra identity, and local work belongs on the compose.yaml "
                "container."
            )
        return self
