"""Settings, and the refusals that keep a misconfigured process from starting. The one worth reading twice
is not a refusal at all: the account session is absent in a working configuration."""

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

    # Telegram publishes two surfaces and they are not two flavours of one thing. This is the bot one:
    # stateless, authorised by a bot token, and the only one a notification ever travels over.
    bot_api_base_url: str = "https://api.telegram.org"

    # `database_user` selects between the two connection modes and is the only switch: set means
    # identity mode over TLS with no credential in the URL, unset means the URL as given, on loopback.
    database_url: str
    database_user: str | None = None

    # Identity mode only, and unset even there when running in Azure — the App Service's
    # system-assigned managed identity needs no configuration.
    azure_client_id: str | None = None
    azure_client_secret: str | None = None
    azure_tenant_id: str | None = None

    # How long this module waits for another process to finish migrating. Five minutes, like
    # polymarket-data: no migration here comes close to the length of a start.
    migration_lock_wait_seconds: float = 300.0

    # Four: this module's work is one HTTP call per message, not a query per row. Seven logical
    # databases share one `B_Standard_B1ms` whose `max_connections` is 35, so every module's number
    # here is one budget — `scripts/tests/test_pool_budget.py` refuses a total above 30.
    database_pool_size: int = 4

    # Creating a bot means talking to Telegram's creator bot, and only a *user account* may. All three
    # together enable it; absent, the module sends normally and refuses to create — a supported state.
    telegram_api_id: int | None = None
    telegram_api_hash: str | None = None
    telegram_session: str | None = None

    # Telegram's own ceiling on how many bots one account may hold. A setting because Telegram raises it
    # on request, and checking it before speaking costs an attempt that counts against the account.
    max_bots: int = 20

    # Telegram refuses a message longer than this, and refusing here rather than truncating is the point:
    # a shortened alert is an alert about something else.
    max_message_chars: int = 4096

    # Easy Auth authorizes an application, not a route. The split here is not reading from writing — both
    # surfaces send — but that creating a bot and binding a destination are REST alone.
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
    def can_create_bots(self) -> bool:
        """Whether the account session needed to reach the creator bot is configured. Its absence is a
        configuration this module supports, so this is a question asked at runtime, not at startup."""
        return (
            self.telegram_api_id is not None
            and bool(self.telegram_api_hash)
            and bool(self.telegram_session)
        )

    @field_validator("bot_api_base_url")
    @classmethod
    def _usable_upstream_url(cls, value: str, info: ValidationInfo) -> str:
        parsed = urlparse(value)
        if not parsed.hostname:
            raise ValueError(f"{str(info.field_name).upper()} is not a usable URL: {value!r}")
        if parsed.scheme not in ("http", "https"):
            raise ValueError(
                f"{str(info.field_name).upper()} must be http or https; got {parsed.scheme!r}"
            )
        return value.rstrip("/")

    @field_validator("database_url")
    @classmethod
    def _not_blank(cls, value: str, info: ValidationInfo) -> str:
        # pydantic already rejects a variable that is absent; this catches the one that is
        # present but empty.
        if not value.strip():
            raise ValueError(f"{str(info.field_name).upper()} is set but empty")
        return value.strip()

    @field_validator("database_user", "telegram_api_hash", "telegram_session")
    @classmethod
    def _blank_means_unset(cls, value: str | None) -> str | None:
        # `TELEGRAM_SESSION=` left in a .env is the same intent as the line being absent, and for
        # DATABASE_USER it is local mode — not a role named "".
        if value is None or not value.strip():
            return None
        return value.strip()

    @model_validator(mode="after")
    def _account_session_is_whole_or_absent(self) -> Settings:
        """Two of the three is the failure worth naming: it looks configured, refuses at the moment the
        operator asks for a bot, and the reason is a variable nobody remembers leaving blank."""
        given = [
            name
            for name, value in (
                ("TELEGRAM_API_ID", self.telegram_api_id),
                ("TELEGRAM_API_HASH", self.telegram_api_hash),
                ("TELEGRAM_SESSION", self.telegram_session),
            )
            if value
        ]
        if given and len(given) < 3:
            raise ValueError(
                "TELEGRAM_API_ID, TELEGRAM_API_HASH and TELEGRAM_SESSION must be given "
                f"together or not at all — only {given} were set, which reaches nothing. "
                "All three absent is a supported configuration: the module sends, and "
                "refuses to create bots."
            )
        return self

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

    @field_validator("max_bots", "max_message_chars", "database_pool_size")
    @classmethod
    def _positive(cls, value: int, info: ValidationInfo) -> int:
        if value < 1:
            raise ValueError(f"{str(info.field_name).upper()} must be at least 1; got {value}")
        return value
