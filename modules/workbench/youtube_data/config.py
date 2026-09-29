"""Settings, and the refusals that keep a misconfigured process from starting. Whether this package runs at all is
decided one level up, by whether its database is configured; everything here is read only once it does."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from pydantic import ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# `prefer`/`allow` still let the client fall back to plaintext if the server does not
# offer TLS — a remote database MUST be reached encrypted, not merely offered it.
_TLS_REQUIRING_SSLMODES = {"require", "verify-ca", "verify-full"}

# What each provider setting may name. The one place a new provider is announced to the configuration.
KNOWN_VIDEO_SOURCES = ("rss", "data_api")
KNOWN_TRANSCRIPT_PROVIDERS = ("direct",)
KNOWN_ANALYSERS = ("openai",)


def _identifiers(raw: str) -> frozenset[str]:
    """A comma-separated setting as a set, with blanks and stray spaces dropped."""
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # `database_user` selects between the two connection modes and is the only switch: set means identity mode over
    # TLS with no credential in the URL, unset means the URL as given, on loopback.
    database_url: str
    database_user: str | None = None

    # Identity mode only, and unset even there when running in Azure.
    azure_client_id: str | None = None
    azure_client_secret: str | None = None
    azure_tenant_id: str | None = None

    # How long this package waits for another process to finish migrating.
    migration_lock_wait_seconds: float = 300.0

    # Two, not three: seven databases share one `B_Standard_B1ms` whose `max_connections` is 50, and
    # `scripts/tests/test_pool_budget.py` holds the total to 30 — which the packages before this one already fill to 29.
    # Enabling this package in production is the change that finds the third connection.
    database_pool_size: int = 2

    # Where films are found, where their words come from and who reads them. Each is a name, so replacing a provider is
    # a line in `.env`; what a name may be is `KNOWN_*` below. `rss` needs nothing and cannot search, measure a film or
    # resolve an `@handle`; `data_api` does all three on a free key.
    video_source: str = "rss"
    data_api_key: str | None = None
    # A list, first choice first; the next is tried only when the one before did not let us in.
    transcript_providers: str = "direct"
    # The languages asked of a transcript, in order of preference.
    transcript_languages: str = "pl,en"

    # The model. Absent key is a supported state, not a refusal — the package discovers and transcribes, and every
    # reading stays empty, which `/state` says.
    analyser: str = "openai"
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    analysis_model: str = "gpt-6-sol"
    # How much of a transcript one reading is given. An hour of speech is ~55k characters; this is well past the
    # longest film the loop accepts, so a cut is the exception and is announced to the model when it happens.
    analysis_max_chars: int = 300_000

    # How this package names itself upstream, and how long it waits for a third party.
    provider_user_agent: str = "tradingcenter-youtube-data/0.1 (+https://github.com/MarekGrzeska)"
    provider_timeout_seconds: float = 20.0

    # Easy Auth authorizes an application, not a route, and both surfaces stand in one process — so which caller
    # reaches which of them is this package's own record.
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
    def transcript_provider_names(self) -> tuple[str, ...]:
        return tuple(part.strip() for part in self.transcript_providers.split(",") if part.strip())

    @property
    def languages(self) -> tuple[str, ...]:
        return tuple(part.strip() for part in self.transcript_languages.split(",") if part.strip())

    @property
    def model_configured(self) -> bool:
        return self.analyser == "openai" and bool(self.openai_api_key and self.openai_api_key.strip())

    @field_validator("database_url", "provider_user_agent", "analysis_model")
    @classmethod
    def _not_blank(cls, value: str, info: ValidationInfo) -> str:
        # pydantic already rejects a variable that is absent; this catches the one that is present but empty.
        if not value.strip():
            raise ValueError(f"{str(info.field_name).upper()} is set but empty")
        return value.strip()

    @field_validator("data_api_key", "openai_api_key", "openai_base_url")
    @classmethod
    def _blank_secret_is_absent(cls, value: str | None) -> str | None:
        # A key line somebody stopped filling means the same as a line that is not there.
        if value is None or not value.strip():
            return None
        return value.strip()

    @field_validator("video_source")
    @classmethod
    def _known_source(cls, value: str) -> str:
        if value not in KNOWN_VIDEO_SOURCES:
            raise ValueError(f"VIDEO_SOURCE must be one of {', '.join(KNOWN_VIDEO_SOURCES)}; got {value!r}")
        return value

    @field_validator("analyser")
    @classmethod
    def _known_analyser(cls, value: str) -> str:
        if value not in KNOWN_ANALYSERS:
            raise ValueError(f"ANALYSER must be one of {', '.join(KNOWN_ANALYSERS)}; got {value!r}")
        return value

    @field_validator("transcript_providers")
    @classmethod
    def _known_transcript_providers(cls, value: str) -> str:
        names = [part.strip() for part in value.split(",") if part.strip()]
        if not names:
            raise ValueError("TRANSCRIPT_PROVIDERS names no provider")
        unknown = [name for name in names if name not in KNOWN_TRANSCRIPT_PROVIDERS]
        if unknown:
            raise ValueError(
                f"TRANSCRIPT_PROVIDERS names {', '.join(unknown)}; the ones this package has are "
                f"{', '.join(KNOWN_TRANSCRIPT_PROVIDERS)}"
            )
        return value

    @field_validator("analysis_max_chars")
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

    @field_validator("database_user")
    @classmethod
    def _blank_means_unset(cls, value: str | None) -> str | None:
        # `DATABASE_USER=` left in a .env is the same intent as the line being absent — local mode.
        if value is None or not value.strip():
            return None
        return value.strip()

    @field_validator("database_pool_size")
    @classmethod
    def _pool_is_usable(cls, value: int) -> int:
        if value < 1:
            raise ValueError(f"DATABASE_POOL_SIZE must be at least 1; got {value}")
        return value

    @model_validator(mode="after")
    def _a_source_that_needs_a_key_has_one(self) -> Settings:
        # A wish and not a state: the source was *asked for*, so running without its key would be a silent downgrade to
        # a source that cannot do what was asked. Absent key for the *model* is the opposite — a supported state.
        if self.video_source == "data_api" and self.data_api_key is None:
            raise ValueError("VIDEO_SOURCE=data_api needs DATA_API_KEY — a free YouTube Data API key")
        return self

    @model_validator(mode="after")
    def _connection_mode_is_coherent(self) -> Settings:
        """The two connection modes, each with its own failure to refuse. Identity mode is off this machine, so TLS and
        no credential; local mode is the URL as given, and must be loopback."""
        parsed = urlparse(self.database_url)
        if self.database_user is not None:
            sslmode = parse_qs(parsed.query).get("sslmode", [None])[0]
            if sslmode not in _TLS_REQUIRING_SSLMODES:
                raise ValueError(
                    f"DATABASE_URL does not require TLS (sslmode={sslmode!r}). With "
                    "DATABASE_USER set this package connects to a database off this "
                    "machine, so the connection MUST be encrypted — set sslmode=require "
                    "(or verify-ca/verify-full)."
                )
            if parsed.username or parsed.password:
                raise ValueError(
                    "DATABASE_URL carries a username or password. With DATABASE_USER set "
                    "this package authenticates with an Entra token fetched at connection "
                    "time — a credential embedded in the URL is not read and should not "
                    "be there."
                )
            return self

        host = (parsed.hostname or "").lower()
        if not (host == "localhost" or host.startswith("127.") or host == "::1"):
            raise ValueError(
                f"DATABASE_URL points at {host!r} with no DATABASE_USER set. Without an "
                "identity this package only connects to a database on this machine's "
                "loopback — a remote database (production included) needs DATABASE_USER "
                "and an Entra identity, and local work belongs on the compose.yaml "
                "container."
            )
        return self
