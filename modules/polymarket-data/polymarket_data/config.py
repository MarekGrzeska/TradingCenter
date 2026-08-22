"""Settings, and the three refusals that keep a misconfigured process from starting.

Two of the three are the shape every module here carries: the database is reached with an
identity or from loopback, never both and never neither. The third is this module's own —
the provider's addresses are settings rather than constants, because both of its surfaces
are public and unauthenticated, and the only thing standing between this module and
somebody else's host is that the value was checked when it was read.
"""

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

    # --- the provider, this module's only upstream ---
    #
    # Two hosts because the provider publishes two surfaces: the metadata one, which names
    # events, their markets and their outcomes and — measured 22 August 2026 — publishes
    # the midpoint of every outcome in one response, and the order-book one, which holds
    # the time series and the per-token quotes.
    gamma_base_url: str = "https://gamma-api.polymarket.com"
    clob_base_url: str = "https://clob.polymarket.com"

    # How this module names itself to the provider. Not politeness: the provider's edge
    # selects on this header and refuses some clients' defaults — `Python-urllib/3.12` gets
    # `403 error code: 1010` on both surfaces, where an absent header, an empty one and
    # httpx's own default are all served (measured 22 August 2026, design.md, measurement 6).
    #
    # A library's default is a value somebody else decides, and its changing on a dependency
    # bump would be an access refusal with no change in this module — and a symptom that
    # reads like a blocked address.
    provider_user_agent: str = "tradingcenter-polymarket-data/0.1 (+https://github.com/MarekGrzeska)"

    # --- the archive's own storage ---
    #
    # `database_user` selects between the two connection modes, and it is the only switch:
    #
    #   set    — identity mode, the production shape. The value is the Postgres role this
    #            module authenticates as; what it authenticates *with* is an Entra token
    #            fetched at connection time. The URL must require TLS and must carry no
    #            credential of its own.
    #   unset  — local mode. `DATABASE_URL` is used exactly as given, password and all,
    #            and must point at this machine's loopback.
    database_url: str
    database_user: str | None = None

    # Identity mode only, and unset even there when running in Azure — the App Service's
    # system-assigned managed identity needs no configuration.
    azure_client_id: str | None = None
    azure_client_secret: str | None = None
    azure_tenant_id: str | None = None

    # How long this module waits for another process to finish migrating before it gives
    # up and refuses to start. Five minutes, not market-data's twenty-five: the biggest
    # table here holds price samples in the tens of thousands per day, not candles in the
    # hundreds of millions, and no migration this module runs comes close to a start.
    migration_lock_wait_seconds: float = 300.0

    # --- how much of the provider's allowance this module may take ---
    #
    # Measured 22 August 2026: 30 sequential calls in 2.5 s (~12/s) drew no refusal. The
    # source application throttled to 6 concurrent and that worked for a year, so 6 is the
    # starting value here — an observation to raise on evidence, not a limit anyone hit.
    provider_concurrency: int = 6

    # Seconds between samples of every tracked event. One request per *event*, not per
    # outcome (design.md, "Próbkowanie idzie przez metadane, nie przez token"), so this
    # multiplied by the tracked-event ceiling is the whole steady-state traffic.
    sample_interval_seconds: int = 60

    # The provider caps one price-history request at 15 days between `startTs` and `endTs`
    # — measured, and on the time interval rather than the point count, so a coarser
    # fidelity does not buy a wider window. A setting rather than a constant because the
    # provider may move it, and a module that silently stopped backfilling would be worse
    # than one that refused.
    history_window_days: int = 15

    # How far back a newly tracked event reaches on its first fill. Divided by the window
    # above, this is a request count: 90 days is six requests per outcome.
    default_backfill_days: int = 90

    # Every tracked event is a request per sample interval, and tracking is a capability of
    # the model. The ceiling counts *events*, not markets, and that is only affordable
    # because one request covers an event however many markets it holds — a single
    # "who wins" event measured at 128 markets on 22 August 2026.
    max_tracked_events: int = 50

    # --- who may reach which surface, once they are through the door ---
    #
    # Easy Auth authorizes an application, not a route. These two lists are what it cannot
    # say: which callers are here for the tool surface at `/mcp` — the workbench — and
    # which are here for the REST contract — the terminal. A caller on neither list is
    # refused even with a token the platform accepted.
    #
    # The split matters more here than in `market-data`, and differently: the tool surface
    # does write, by design, but only to the list of observations. Deleting collected
    # history lives on the REST contract alone, and this record is what keeps it there.
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
        # pydantic already rejects a variable that is absent; this catches the one that is
        # present but empty, which is what an unfilled .env actually looks like. The
        # user-agent is in this list because an empty value here would send the header
        # empty and leave the module unnamed to a provider that reads it.
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
        """The two connection modes, each with its own failure to refuse.

        Identity mode (`database_user` set): the database is off this machine, so the URL
        must require TLS and must not carry a credential that would never be read anyway.

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
