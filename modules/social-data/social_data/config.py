"""Settings, and the refusals that keep a misconfigured process from starting. The one refusal this module does
not make is about the model: without a key it collects and does not enrich, which is a supported state."""

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

    # The feed the one source reads. A setting rather than a constant because it is somebody's
    # side project, and the day it moves is a deployment, not a release.
    truth_social_feed_url: str = "https://www.trumpstruth.org/feed"

    # How this module names itself upstream. Not politeness: an edge that selects on this header
    # refuses some defaults outright, which reads as an empty feed.
    provider_user_agent: str = "tradingcenter-social-data/0.1 (+https://github.com/MarekGrzeska)"

    provider_timeout_seconds: float = 20.0

    # `database_user` selects between the two connection modes and is the only switch: set means
    # identity mode over TLS with no credential in the URL, unset means the URL as given, on loopback.
    database_url: str
    database_user: str | None = None

    # Identity mode only, and unset even there when running in Azure — the App Service's
    # system-assigned managed identity needs no configuration.
    azure_client_id: str | None = None
    azure_client_secret: str | None = None
    azure_tenant_id: str | None = None

    # How long this module waits for another process to finish migrating.
    migration_lock_wait_seconds: float = 300.0

    # Seconds between passes over the feed. Posts arrive in bursts and the feed is one request per
    # date, so this is minutes rather than the archive's seconds.
    collect_interval_seconds: int = 300

    # How far back one pass looks. Also the window the enrichment works over, and the window the
    # screens ask for by default.
    collect_window_hours: int = 24

    # Ticks without a successful collection before the archive calls itself stale. Five minutes of
    # silence is a slow feed; half an hour of it is something to say on the screen.
    stale_after_ticks: int = 6

    # The model, and the two jobs it does. Absent key is a supported state, not a refusal — the
    # module collects and leaves every reading empty.
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    translation_model: str = "gpt-5.6-luna"
    analysis_model: str = "gpt-5.6-terra"

    # How many posts one pass may enrich. The ceiling exists for the same reason the window does:
    # a busy day must cost a bounded amount, and the rest waits for the next pass.
    enrichment_batch_limit: int = 20

    # Easy Auth authorizes an application, not a route, and both surfaces stand in one process — so
    # which caller reaches which of them is this module's own record.
    require_authenticated_principal: bool = False
    tool_caller_application_ids: str = ""
    rest_caller_application_ids: str = ""

    @property
    def tool_caller_ids(self) -> frozenset[str]:
        return _identifiers(self.tool_caller_application_ids)

    @property
    def rest_caller_ids(self) -> frozenset[str]:
        return _identifiers(self.rest_caller_application_ids)

    @property
    def model_configured(self) -> bool:
        return bool(self.openai_api_key and self.openai_api_key.strip())

    @field_validator("truth_social_feed_url", "openai_base_url")
    @classmethod
    def _usable_url(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None or not value.strip():
            return None if info.field_name == "openai_base_url" else value
        parsed = urlparse(value)
        if not parsed.hostname:
            raise ValueError(f"{str(info.field_name).upper()} is not a usable URL: {value!r}")
        if parsed.scheme not in ("http", "https"):
            raise ValueError(
                f"{str(info.field_name).upper()} must be http or https; got {parsed.scheme!r}"
            )
        return value.rstrip("/")

    @field_validator("database_url", "provider_user_agent", "translation_model", "analysis_model")
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
        "collect_interval_seconds",
        "collect_window_hours",
        "stale_after_ticks",
        "enrichment_batch_limit",
    )
    @classmethod
    def _positive(cls, value: int, info: ValidationInfo) -> int:
        if value < 1:
            raise ValueError(f"{str(info.field_name).upper()} must be at least 1; got {value}")
        return value

    @field_validator("provider_timeout_seconds")
    @classmethod
    def _positive_seconds(cls, value: float, info: ValidationInfo) -> float:
        if value <= 0:
            raise ValueError(f"{str(info.field_name).upper()} must be positive; got {value}")
        return value
