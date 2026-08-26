"""Settings, and the three refusals that keep a misconfigured process from starting. The third is this
module's own: both provider surfaces are public, so the only guard is that the address was checked."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from pydantic import ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# `prefer`/`allow` still let the client fall back to plaintext if the server does not
# offer TLS — a remote database MUST be reached encrypted, not merely offered it.
_TLS_REQUIRING_SSLMODES = {"require", "verify-ca", "verify-full"}


def _identifiers(raw: str) -> frozenset[str]:
    """A comma-separated setting as a set, with blanks and stray spaces dropped."""
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Two hosts because the provider publishes two surfaces: the metadata one, which publishes every
    # outcome's midpoint in one response, and the order-book one, which holds the time series.
    gamma_base_url: str = "https://gamma-api.polymarket.com"
    clob_base_url: str = "https://clob.polymarket.com"

    # How this module names itself to the provider. Not politeness: the edge selects on this header
    # and refuses some defaults — `Python-urllib/3.12` gets `403 error code: 1010` on both surfaces.
    provider_user_agent: str = "tradingcenter-polymarket-data/0.1 (+https://github.com/MarekGrzeska)"

    # `database_user` selects between the two connection modes and is the only switch: set means
    # identity mode over TLS with no credential in the URL, unset means the URL as given, on loopback.
    database_url: str
    database_user: str | None = None

    # Identity mode only, and unset even there when running in Azure — the App Service's
    # system-assigned managed identity needs no configuration.
    azure_client_id: str | None = None
    azure_client_secret: str | None = None
    azure_tenant_id: str | None = None

    # How long this module waits for another process to finish migrating. Five minutes, not
    # market-data's twenty-five: no migration here comes close to the length of a start.
    migration_lock_wait_seconds: float = 300.0

    # Measured 22 August 2026: 30 sequential calls in 2.5 s drew no refusal. The source application
    # throttled to 6 for a year, so 6 is the starting value — to raise on evidence, not a limit hit.
    provider_concurrency: int = 6

    # Seconds between samples of every tracked event. One request per *event*, not per outcome, so
    # this multiplied by the tracked-event ceiling is the whole steady-state traffic.
    sample_interval_seconds: int = 60

    # The provider caps one price-history request at 15 days, measured — and on the interval rather
    # than the point count, so a coarser fidelity buys no width. A setting because the provider may move it.
    history_window_days: int = 15

    # How far back a newly tracked event reaches on its first fill. Divided by the window
    # above, this is a request count: 90 days is six requests per outcome.
    default_backfill_days: int = 90

    # The ceiling counts *events*, not markets, and that is only affordable because one request covers
    # an event however many markets it holds — one measured at 128 on 22 August 2026.
    max_tracked_events: int = 50

    # Easy Auth authorizes an application, not a route. The split matters differently here: the tool
    # surface does write, but only to the list of observations. Deleting history is REST alone.
    require_authenticated_principal: bool = False
    tool_caller_application_ids: str = ""
    rest_caller_application_ids: str = ""

    @property
    def tool_caller_ids(self) -> frozenset[str]:
        return _identifiers(self.tool_caller_application_ids)

    @property
    def rest_caller_ids(self) -> frozenset[str]:
        return _identifiers(self.rest_caller_application_ids)

    @field_validator("gamma_base_url", "clob_base_url")
    @classmethod
    def _usable_provider_url(cls, value: str, info: ValidationInfo) -> str:
        parsed = urlparse(value)
        if not parsed.hostname:
            raise ValueError(f"{str(info.field_name).upper()} is not a usable URL: {value!r}")
        if parsed.scheme not in ("http", "https"):
            raise ValueError(
                f"{str(info.field_name).upper()} must be http or https; got {parsed.scheme!r}"
            )
        return value.rstrip("/")

    @field_validator("database_url", "provider_user_agent")
    @classmethod
    def _not_blank(cls, value: str, info: ValidationInfo) -> str:
        # pydantic already rejects a variable that is absent; this catches the one that is present
        # but empty. The user-agent is in the list because an empty one leaves the module unnamed.
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

    @field_validator(
        "provider_concurrency",
        "sample_interval_seconds",
        "history_window_days",
        "default_backfill_days",
        "max_tracked_events",
    )
    @classmethod
    def _positive(cls, value: int, info: ValidationInfo) -> int:
        if value < 1:
            raise ValueError(f"{str(info.field_name).upper()} must be at least 1; got {value}")
        return value
