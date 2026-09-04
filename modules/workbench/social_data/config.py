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

    # Three, for polymarket-data's reason: collecting is one pass, and nothing here writes on a
    # request. Seven databases share one `B_Standard_B1ms` whose `max_connections` is 35 —
    # `scripts/tests/test_pool_budget.py` refuses a total above 30.
    database_pool_size: int = 3

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

    # The door to Telegram, and the setting whose *absence* is a working configuration: without it
    # the module collects and reads exactly as before and tells nobody, which `/state` reports.
    # The three go together — an address with no destination is a message with nowhere to go.
    telegram_gateway_url: str | None = None
    telegram_gateway_scope: str | None = None
    alert_destination: str | None = None

    # How impactful a post must be to be worth a notification. Eight rather than five: the operator
    # reads every one of these on a phone, and a channel that speaks daily is one nobody looks at.
    alert_min_impact_score: int = 8

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

    @property
    def alerts_configured(self) -> bool:
        """Whether this deployment can tell anybody anything. Asked at runtime rather than refused
        at startup: silence is a state this module supports, and one it reports."""
        return bool(self.telegram_gateway_url and self.alert_destination)

    @field_validator("database_pool_size")
    @classmethod
    def _pool_is_usable(cls, value: int) -> int:
        if value < 1:
            raise ValueError(f"DATABASE_POOL_SIZE must be at least 1; got {value}")
        return value

    @field_validator("truth_social_feed_url", "openai_base_url", "telegram_gateway_url")
    @classmethod
    def _usable_url(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None or not value.strip():
            # The feed has a default and is never unset; the other two are optional, and a line
            # somebody stopped filling means the same as a line that is not there.
            return value if info.field_name == "truth_social_feed_url" else None
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

    @field_validator("database_user", "telegram_gateway_scope", "alert_destination")
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

    @field_validator("alert_min_impact_score")
    @classmethod
    def _within_the_score_range(cls, value: int) -> int:
        # The reading is 1..10, so a threshold outside it is a channel that is either silent for
        # ever or one that says everything — both of which look like a working configuration.
        if not 1 <= value <= 10:
            raise ValueError(f"ALERT_MIN_IMPACT_SCORE must be between 1 and 10; got {value}")
        return value

    @model_validator(mode="after")
    def _the_gateway_is_whole_or_absent(self) -> Settings:
        """An address, a destination, and — off this machine — a scope. Named as a refusal because
        each partial form is silence that reads like a working configuration."""
        if self.telegram_gateway_url is None:
            if self.telegram_gateway_scope or self.alert_destination:
                raise ValueError(
                    "TELEGRAM_GATEWAY_SCOPE or ALERT_DESTINATION is set without "
                    "TELEGRAM_GATEWAY_URL — there is no gateway for either to describe. All "
                    "three absent is a supported configuration: the module collects and tells "
                    "nobody, which /state reports."
                )
            return self

        if not self.alert_destination:
            raise ValueError(
                "TELEGRAM_GATEWAY_URL is set without ALERT_DESTINATION — the gateway addresses "
                "by the name the operator bound, and a message with no destination has nowhere "
                "to go."
            )

        host = (urlparse(self.telegram_gateway_url).hostname or "").lower()
        loopback = host == "localhost" or host.startswith("127.") or host == "::1"
        if loopback and self.telegram_gateway_scope:
            raise ValueError(
                "TELEGRAM_GATEWAY_SCOPE is set for a gateway on this machine's loopback, where "
                "there is no directory to ask for a token."
            )
        if not loopback and not self.telegram_gateway_scope:
            raise ValueError(
                "TELEGRAM_GATEWAY_URL points off this machine and TELEGRAM_GATEWAY_SCOPE is "
                "not set — the gateway is behind Easy Auth, which refuses a request carrying "
                "no token before the module sees it."
            )
        return self
