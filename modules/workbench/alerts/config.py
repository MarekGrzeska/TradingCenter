"""Settings, and the refusals that keep a misconfigured process from starting. Whether this package runs at all is
decided one level up, by whether its database is configured; everything here is read only once it does."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from pydantic import Field, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# `prefer`/`allow` still let the client fall back to plaintext if the server does not
# offer TLS — a remote database MUST be reached encrypted, not merely offered it.
_TLS_REQUIRING_SSLMODES = {"require", "verify-ca", "verify-full"}


def _identifiers(raw: str) -> frozenset[str]:
    """A comma-separated setting as a set, with blanks and stray spaces dropped."""
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # `database_user` selects between the two connection modes and is the only switch: set means identity mode over
    # TLS with no credential in the URL, unset means the URL as given, on loopback.
    # Out of the repr: a server's URL carries its role's password, and a failed validation prints the model.
    database_url: str = Field(repr=False)
    database_user: str | None = None
    # Hosts on the container network of this machine (`PRIVATE_HOSTS`, comma-separated), reached with the password in the
    # URL — a database that is not on loopback and still never leaves the machine. Empty everywhere but a server.
    private_hosts: str = ""

    # Identity mode only, and unset even there when running in Azure.
    azure_client_id: str | None = None
    azure_client_secret: str | None = None
    azure_tenant_id: str | None = None

    # How long this package waits for another process to finish migrating.
    migration_lock_wait_seconds: float = 300.0

    # Two: the clock holds one connection for a claim and the routes the other, and
    # `scripts/tests/test_pool_budget.py` holds the total across every package.
    database_pool_size: int = 2

    # How often the clock wakes. A published event wakes it at once, so this is only how late a value rule can be.
    tick_seconds: float = 5.0
    # The shortest a rule may wait between two looks at its value. Each look is a tool call against an archive, and the
    # archives' own data moves in minutes; a rule faster than this costs the database and sees nothing.
    min_interval_seconds: int = 30
    # How long a delivery that could not be made is tried again before it is let go. A film announced a day late, in a
    # heap with twenty others, is worse than the silence it replaced.
    retry_window_hours: int = 6
    # The most messages one rule may deliver in an hour; the rest are recorded as throttled and never sent.
    max_per_hour: int = 20
    # How long a published event is kept. The fires it caused stay, with the text that was sent.
    event_retention_days: int = 30

    # The sentence-to-rule draft. Its own line of the bill, like the teams' beside the conversation's; absent is a
    # supported state — everything but drafting works, and `/state` says so.
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    draft_model: str = "gpt-6-luna"
    draft_daily_token_limit: int = 200_000

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
    def drafting(self) -> bool:
        """Whether a sentence can be turned into a draft at all."""
        return self.openai_api_key is not None

    @field_validator("database_url", "draft_model")
    @classmethod
    def _not_blank(cls, value: str, info: ValidationInfo) -> str:
        # pydantic already rejects a variable that is absent; this catches the one that is present but empty.
        if not value.strip():
            raise ValueError(f"{str(info.field_name).upper()} is set but empty")
        return value.strip()

    @field_validator("openai_api_key", "openai_base_url")
    @classmethod
    def _blank_secret_is_absent(cls, value: str | None) -> str | None:
        # A key line somebody stopped filling means the same as a line that is not there.
        if value is None or not value.strip():
            return None
        return value.strip()

    @field_validator("database_user")
    @classmethod
    def _blank_means_unset(cls, value: str | None) -> str | None:
        # `DATABASE_USER=` left in a .env is the same intent as the line being absent — local mode.
        if value is None or not value.strip():
            return None
        return value.strip()

    @field_validator(
        "min_interval_seconds",
        "retry_window_hours",
        "max_per_hour",
        "event_retention_days",
        "draft_daily_token_limit",
        "database_pool_size",
    )
    @classmethod
    def _positive(cls, value: int, info: ValidationInfo) -> int:
        if value < 1:
            raise ValueError(f"{str(info.field_name).upper()} must be at least 1; got {value}")
        return value

    @field_validator("tick_seconds")
    @classmethod
    def _positive_seconds(cls, value: float, info: ValidationInfo) -> float:
        if value <= 0:
            raise ValueError(f"{str(info.field_name).upper()} must be positive; got {value}")
        return value

    @property
    def private_host_names(self) -> frozenset[str]:
        return frozenset(h.strip().lower() for h in self.private_hosts.split(",") if h.strip())

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
        loopback = host == "localhost" or host.startswith("127.") or host == "::1"
        if not (loopback or host in self.private_host_names):
            raise ValueError(
                f"DATABASE_URL points at {host!r} with no DATABASE_USER set. Without an "
                "identity this package only connects to a database on this machine's "
                "loopback, or a host of PRIVATE_HOSTS — a remote database (production included) needs DATABASE_USER "
                "and an Entra identity, and local work belongs on the compose.yaml "
                "container."
            )
        if not loopback and not (parsed.username and parsed.password):
            raise ValueError(
                f"DATABASE_URL points at the private host {host!r} without a role and password. On a server "
                "this module connects as its own role, which owns its database — the URL must name it."
            )
        return self
