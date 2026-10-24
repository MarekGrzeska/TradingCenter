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

    # Two: the run queue holds one connection while it writes a report and the routes the other, and
    # `scripts/tests/test_pool_budget.py` holds the total across every package.
    database_pool_size: int = 2

    # How many runs compute at once, each in a worker process of its own. One by default: a run is CPU for minutes, and
    # this process also serves the candle stream and the conversation.
    run_concurrency: int = 1
    # The most `MINUTE` candles of the traded instrument one run may read, refused before queueing: about four years of
    # a 24-hour market, sized from the measurement in PR #352.
    max_minute_bars: int = 1_500_000
    # How long one run may compute before it is stopped and recorded as failed, with that reason.
    run_timeout_seconds: float = 600.0
    # How many times the random-entry benchmark is drawn. Its median and percentiles are only as steady as this.
    random_entry_repetitions: int = 200

    # The operator's screen, and nobody else: what this package holds is research the operator decides on. There is no
    # tool surface, so there is no tool caller list.
    require_authenticated_principal: bool = False
    rest_caller_application_ids: str = ""

    @property
    def rest_caller_ids(self) -> frozenset[str]:
        return _identifiers(self.rest_caller_application_ids)

    @field_validator("database_url")
    @classmethod
    def _not_blank(cls, value: str, info: ValidationInfo) -> str:
        # pydantic already rejects a variable that is absent; this catches the one that is present but empty.
        if not value.strip():
            raise ValueError(f"{str(info.field_name).upper()} is set but empty")
        return value.strip()

    @field_validator("database_user")
    @classmethod
    def _blank_means_unset(cls, value: str | None) -> str | None:
        # `DATABASE_USER=` left in a .env is the same intent as the line being absent — local mode.
        if value is None or not value.strip():
            return None
        return value.strip()

    @field_validator("database_pool_size", "run_concurrency", "max_minute_bars", "random_entry_repetitions")
    @classmethod
    def _positive(cls, value: int, info: ValidationInfo) -> int:
        if value < 1:
            raise ValueError(f"{str(info.field_name).upper()} must be at least 1; got {value}")
        return value

    @field_validator("run_timeout_seconds")
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
