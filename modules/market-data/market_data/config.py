"""Settings, and the guard that keeps this module behind the gateway.

The guard here mirrors the one in `capital-gateway`'s config, for the same kind of
reason. That module refuses to start against a live host because a runtime check would
leave an authenticated live session sitting in the process. This one refuses to start
against capital.com at all.

capital.com counts its 10 requests/second against the *account*, not the process. A
second client anywhere — another process, another machine — is a second budget spent
from the same allowance, and the provider answers the overflow with a rate-limit error
that reaches a caller looking exactly like missing data. The gateway owns the only
rate gate; this module is a consumer of the gateway's contract and nothing else.

Refusing to build the settings leaves nothing running to misuse.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from pydantic import ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Any host carrying this belongs to the provider. Matched as a substring on purpose:
# the demo, live and streaming hosts are all variants of it, and a rule tight enough
# to name one of them is loose enough to let the others through.
PROVIDER_HOST_MARKER = "capital.com"

# `prefer`/`allow` still let the client fall back to plaintext if the server does not
# offer TLS — specs/market-data-database-connection, "Połączenie z bazą jest
# szyfrowane" requires the connection MUST be encrypted, not merely offered it.
_TLS_REQUIRING_SSLMODES = {"require", "verify-ca", "verify-full"}


def _identifiers(raw: str) -> frozenset[str]:
    """A comma-separated setting as a set, with blanks and stray spaces dropped."""
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- the gateway, this module's only upstream ---
    gateway_base_url: str = "http://localhost:8010"
    gateway_stream_url: str = "ws://localhost:8010/ws/stream"
    # capital-gateway is not public — every REST call and every stream handshake must
    # carry this, or the gateway answers 401 before capital.com is touched. Required,
    # not defaulted: a module that started without it would run and archive nothing,
    # and the gap would surface as silence hours later instead of as a refusal now.
    gateway_api_key: str

    # --- the archive's own storage ---
    #
    # `database_user` selects between the module's two connection modes, and it is the
    # only switch (openspec: market-data-database-connection):
    #
    #   set    — identity mode, the remote/production shape. The value is the Postgres
    #            role this module authenticates as; what it authenticates *with* is an
    #            Entra token fetched at connection time (db.py). The URL must require
    #            TLS and must not carry a credential of its own.
    #   unset  — local mode. `DATABASE_URL` is used exactly as given, password and all,
    #            and must point at this machine's loopback — without an identity this
    #            module refuses to reach beyond localhost, so a `.env` pointing at
    #            production is a startup error rather than a quiet write.
    database_url: str
    database_user: str | None = None

    # Identity mode only, and unset even there when running in Azure — the App Service's
    # system-assigned managed identity needs no configuration, `db.py`'s
    # `DefaultAzureCredential` finds it on its own.
    azure_client_id: str | None = None
    azure_client_secret: str | None = None
    azure_tenant_id: str | None = None

    # How long this module waits for another process to finish migrating before it gives
    # up and refuses to start. Twenty-five minutes, against the agent's five: the candle
    # table is the largest thing in this system, and an index rebuilt over it takes far
    # longer than a start. A wait shorter than the migration ahead of it turns a slow
    # migration into a restart loop that never finishes one
    # (`market-data-database-connection`, "Kres MUST być dłuższy niż najdłuższa
    # migracja").
    #
    # Not thirty: App Service caps `WEBSITES_CONTAINER_START_TIME_LIMIT` at 1800s
    # (`infra/app-service.tf`), and this module has to be the one that gives up first.
    # The platform giving up first restarts the container, which starts the same
    # migration again and says nothing about why.
    migration_lock_wait_seconds: float = 1500.0

    # --- how much of the provider's allowance this module may take ---
    #
    # One backfill at a time by default. A deep read is dozens of back-to-back requests
    # through the gateway's shared rate gate, so two of them running together are enough
    # to starve the chart an operator is looking at right now.
    backfill_concurrency: int = 1

    # How far back a newly tracked pair reaches on its first fill. The gateway pages past
    # the provider's 1000-row ceiling itself, so this is a candle count, not a page count.
    default_backfill_bars: int = 5000

    # The gateway holds one provider connection per (symbol, resolution) and the provider
    # limits how many a session may hold. The ceiling is therefore real, and it is a budget
    # to raise on evidence, not a guess to discover by having the feed die.
    #
    # It counts pairs, not instruments — the earlier 20 read as "20 instruments" and was
    # spent by three. One instrument watched across every `Resolution` is 8 pairs, so the
    # number below is 20 instruments' worth of them.
    max_tracked_pairs: int = 160

    # An indicator computation is a Python loop for every recursive filter it touches, and
    # that loop holds the GIL — a thread would not free the event loop the way it does for
    # I/O, so the limit here is a plain gate, not a pool. Bounds how many `POST
    # /indicators/*` requests compute at once, so one asking for many indicators over a
    # long range cannot stall the candle stream every other request depends on.
    indicator_concurrency: int = 4

    # --- how a browser gets in ---
    #
    # A ticket is minted for one handshake and dies on use (`tickets.py`). This is the
    # window between asking for one and spending it: enough for a slow network, short
    # enough that a ticket sitting in a log is worthless long before anyone reads it.
    # Single use is the real protection — this is the second line, for the ticket nobody
    # ever spent.
    stream_ticket_ttl_seconds: int = 30

    # Whether a platform authenticator stands in front of this module. Where it does,
    # only a caller it has already identified may be handed a ticket, and a request
    # arriving without an identity is refused rather than served.
    #
    # The module MUST NOT simply assume the layer in front is doing its job: one wrong
    # line in Terraform would otherwise leave a ticket factory open to the internet —
    # which is an open stream — and nothing about it would look wrong from here. Set in
    # Azure (`infra/app-service.tf`); off locally, where nothing stands in front and
    # there is no identity to have.
    require_authenticated_principal: bool = False

    # --- who may reach which surface, once they are through the door ---
    #
    # Easy Auth authorizes an application, not a route (`caller_access.py`). These two
    # lists are what it cannot say: which callers are here for the tool surface at `/mcp`
    # — `agent` and `teams`, which must never reach the routes that start collecting a
    # pair or delete one — and which are here for the REST contract, which is the
    # terminal. A caller on neither list is refused even with a token the platform
    # accepted.
    #
    # Comma-separated application identifiers rather than names: a name is a description,
    # an identifier is what arrives in the header. Empty locally, where
    # `require_authenticated_principal` is off and there is no identity to match — the
    # lists are read only where that requirement is on.
    tool_caller_application_ids: str = ""
    rest_caller_application_ids: str = ""

    @property
    def tool_caller_ids(self) -> frozenset[str]:
        return _identifiers(self.tool_caller_application_ids)

    @property
    def rest_caller_ids(self) -> frozenset[str]:
        return _identifiers(self.rest_caller_application_ids)

    @field_validator("gateway_base_url", "gateway_stream_url")
    @classmethod
    def _not_the_provider(cls, value: str, info: ValidationInfo) -> str:
        host = (urlparse(value).hostname or "").lower()
        if not host:
            raise ValueError(f"{str(info.field_name).upper()} is not a usable URL: {value!r}")
        if PROVIDER_HOST_MARKER in host:
            raise ValueError(
                f"{str(info.field_name).upper()} points at capital.com ({value!r}). This module "
                "talks to capital-gateway, never to the provider — the gateway owns the single "
                "rate gate and the demo-only guard, and going around it breaks both."
            )
        return value.rstrip("/")

    @field_validator("database_url", "gateway_api_key")
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

    @model_validator(mode="after")
    def _connection_mode_is_coherent(self) -> Settings:
        """The two connection modes, each with its own failure to refuse.

        Identity mode (`database_user` set — production's shape, `infra/app-service.tf`):
        the database is off this machine, so the URL must require TLS and must not carry
        a credential that would never be read anyway.

        Local mode (`database_user` unset): the URL is used exactly as given, password
        and all — and must point at loopback. Without an identity this module refuses to
        reach beyond this machine: a `.env` aimed at production fails here at startup
        instead of quietly writing (openspec: market-data-database-connection, "Praca bez
        tożsamości nie wychodzi poza maszynę").
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
        "backfill_concurrency",
        "default_backfill_bars",
        "max_tracked_pairs",
        "stream_ticket_ttl_seconds",
        "indicator_concurrency",
    )
    @classmethod
    def _positive(cls, value: int, info: ValidationInfo) -> int:
        if value < 1:
            raise ValueError(f"{str(info.field_name).upper()} must be at least 1; got {value}")
        return value
