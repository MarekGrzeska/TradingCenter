"""Settings, and the four ways this module refuses to start rather than misbehave.

Three of them are the database rule every schema in this repository carries — identity or
loopback, never both and never neither, and TLS wherever the database is off this machine.
The fourth is this module's own: the archive is its only upstream, and a URL that is not
one is a module that would run and decide nothing.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from pydantic import ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# `prefer`/`allow` still let the client fall back to plaintext if the server does not
# offer TLS — `strategy-database-connection` requires the connection MUST be encrypted,
# not merely offered it.
_TLS_REQUIRING_SSLMODES = {"require", "verify-ca", "verify-full"}


def _identifiers(raw: str) -> frozenset[str]:
    """A comma-separated setting as a set, with blanks and stray spaces dropped."""
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- the archive, this module's only upstream ---
    #
    # The REST contract, not the tool surface at `/mcp`: that surface is deliberately
    # narrowed for a model — ten indicators a call, two hundred points a series — which is
    # right for an agent and too tight for a loop (design.md, decision 2).
    market_data_url: str = "http://localhost:8020"
    # The archive's own audience, when this module has an identity to present to it.
    # Absent is a working configuration and the local one: without a directory there is no
    # token to get. Set, every request carries a bearer token for this module's identity —
    # which market-data matches against its `REST_CALLER_APPLICATION_IDS`.
    market_data_scope: str | None = None
    market_data_request_timeout_seconds: float = 30.0

    # --- this module's own storage ---
    #
    # `database_user` selects between the two connection modes, and it is the only switch
    # (`strategy-database-connection`):
    #
    #   set    — identity mode, the remote/production shape. The value is the Postgres
    #            role this module authenticates as; what it authenticates *with* is an
    #            Entra token fetched at connection time. The URL must require TLS and must
    #            not carry a credential of its own.
    #   unset  — local mode. `DATABASE_URL` is used exactly as given, password and all,
    #            and must point at this machine's loopback.
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

    # --- the loop ---
    #
    # How often the loop wakes to ask whether a new bar has closed. Not the resolution it
    # decides on: a strategy on HOUR closes twelve of these apart, and waking more often
    # than the bar closes costs one cheap query that finds nothing new.
    evaluation_interval_seconds: int = 60

    # --- who may reach which surface ---
    #
    # Whether a platform authenticator stands in front of this module. Where it does, a
    # request arriving without an identity is refused rather than served. The module MUST
    # NOT simply assume the layer in front is doing its job — one wrong line in Terraform
    # would otherwise leave both surfaces open, and nothing about it would look wrong from
    # here.
    require_authenticated_principal: bool = False

    # Easy Auth authorizes an application, not a route. These two lists are what it cannot
    # say: which callers are here for the read-only tool surface at `/mcp` — the workbench,
    # whose triggers read `pending_setups` — and which are here for the REST contract,
    # which is the terminal and the operator.
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
        """The two connection modes, each with its own failure to refuse.

        Identity mode (`database_user` set — production's shape): the database is off this
        machine, so the URL must require TLS and must not carry a credential that would
        never be read anyway.

        Local mode (`database_user` unset): the URL is used exactly as given, password and
        all — and must point at loopback. Without an identity this module refuses to reach
        beyond this machine, so a `.env` aimed at production fails here at startup instead
        of quietly writing.
        """
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
