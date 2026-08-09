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

from pydantic import ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Any host carrying this belongs to the provider. Matched as a substring on purpose:
# the demo, live and streaming hosts are all variants of it, and a rule tight enough
# to name one of them is loose enough to let the others through.
PROVIDER_HOST_MARKER = "capital.com"

# `prefer`/`allow` still let the client fall back to plaintext if the server does not
# offer TLS — specs/market-data-database-connection, "Połączenie z bazą jest
# szyfrowane" requires the connection MUST be encrypted, not merely offered it.
_TLS_REQUIRING_SSLMODES = {"require", "verify-ca", "verify-full"}


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
    # No password here, ever (design.md, "Do bazy — tożsamość, do capital.com — Key
    # Vault"): `database_user` is the role this module authenticates as, and what it
    # authenticates *with* is an Entra token fetched at connection time (db.py), not
    # anything held in configuration. `sslmode=require` (or stricter) is mandatory in
    # the URL — see `_requires_tls` below.
    database_url: str
    database_user: str

    # Unset in Azure — the App Service's own system-assigned managed identity needs no
    # configuration, `db.py`'s `DefaultAzureCredential` finds it on its own. Set locally,
    # together, to the dev service principal's credentials (`sp-tradingcenter-market-data-dev`,
    # `infra/entra.tf`): there is no ambient identity on a developer's machine.
    azure_client_id: str | None = None
    azure_client_secret: str | None = None
    azure_tenant_id: str | None = None

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
    # limits how many a session may hold. The ceiling is therefore real, and the number
    # below is deliberately conservative: it is a budget to raise on evidence, not a
    # guess to discover by having the feed die.
    max_tracked_pairs: int = 20

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

    @field_validator("database_url", "database_user", "gateway_api_key")
    @classmethod
    def _not_blank(cls, value: str, info: ValidationInfo) -> str:
        # pydantic already rejects a variable that is absent; this catches the one that is
        # present but empty, which is what an unfilled .env actually looks like.
        if not value.strip():
            raise ValueError(f"{str(info.field_name).upper()} is set but empty")
        return value.strip()

    @field_validator("database_url")
    @classmethod
    def _requires_tls(cls, value: str) -> str:
        sslmode = parse_qs(urlparse(value).query).get("sslmode", [None])[0]
        if sslmode not in _TLS_REQUIRING_SSLMODES:
            raise ValueError(
                f"DATABASE_URL does not require TLS (sslmode={sslmode!r}). The database "
                "is off this machine, so the connection to it MUST be encrypted — set "
                "sslmode=require (or verify-ca/verify-full)."
            )
        return value

    @field_validator("database_url")
    @classmethod
    def _no_embedded_credential(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.username or parsed.password:
            raise ValueError(
                "DATABASE_URL carries a username or password. This module authenticates "
                "with an Entra token fetched at connection time (DATABASE_USER selects "
                "the role) — a credential embedded in the URL is not read and should not "
                "be there."
            )
        return value

    @field_validator(
        "backfill_concurrency",
        "default_backfill_bars",
        "max_tracked_pairs",
        "stream_ticket_ttl_seconds",
    )
    @classmethod
    def _positive(cls, value: int, info: ValidationInfo) -> int:
        if value < 1:
            raise ValueError(f"{str(info.field_name).upper()} must be at least 1; got {value}")
        return value
