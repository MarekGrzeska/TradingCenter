"""Settings, and the guard that keeps this module behind the gateway. capital.com counts its 10
requests/second per account, and the gateway owns the only rate gate; this module is a consumer."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from pydantic import ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Any host carrying this belongs to the provider. A substring on purpose: demo, live and streaming
# are all variants, and a rule tight enough to name one lets the others through.
PROVIDER_HOST_MARKER = "capital.com"

# `prefer`/`allow` still let the client fall back to plaintext if the server offers no TLS, and the
# spec requires the connection MUST be encrypted, not merely offered it.
_TLS_REQUIRING_SSLMODES = {"require", "verify-ca", "verify-full"}


def _identifiers(raw: str) -> frozenset[str]:
    """A comma-separated setting as a set, with blanks and stray spaces dropped."""
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    gateway_base_url: str = "http://localhost:8010"
    gateway_stream_url: str = "ws://localhost:8010/ws/stream"
    # capital-gateway is not public — every call must carry this or the gateway answers 401.
    # Required, not defaulted: without it the module archives nothing and the gap surfaces later.
    gateway_api_key: str
    # The gateway's own audience, when this module has an identity to present. Absent is a working
    # configuration and the local one. The stream is not covered: `/ws/stream` is outside the door.
    gateway_scope: str | None = None

    # `database_user` selects between the two connection modes and is the only switch: set means
    # identity mode over TLS with no credential in the URL, unset means the URL as given, on loopback.
    database_url: str
    database_user: str | None = None

    # Identity mode only, and unset even there when running in Azure: the App Service's
    # system-assigned identity needs no configuration, `DefaultAzureCredential` finds it.
    azure_client_id: str | None = None
    azure_client_secret: str | None = None
    azure_tenant_id: str | None = None

    # How long this module waits for another process to finish migrating. Twenty-five minutes against
    # the agent's five, and not thirty: App Service caps the container start at 1800s and must not win.
    migration_lock_wait_seconds: float = 1500.0

    # One backfill at a time by default: a deep read is dozens of back-to-back requests through the
    # gateway's shared rate gate, and two together starve the chart an operator is looking at.
    backfill_concurrency: int = 1

    # How far back a newly tracked pair reaches on its first fill. The gateway pages past
    # the provider's 1000-row ceiling itself, so this is a candle count, not a page count.
    default_backfill_bars: int = 5000

    # The gateway holds one provider connection per (symbol, resolution), and the provider limits how
    # many a session may hold. It counts pairs, not instruments: the earlier 20 was spent by three.
    max_tracked_pairs: int = 160

    # An indicator computation is a Python loop holding the GIL, so this is a plain gate, not a pool.
    # One request asking for many indicators cannot stall the candle stream the rest depends on.
    indicator_concurrency: int = 4

    # The window between asking for a ticket and spending it: long enough for a slow network, short
    # enough that a ticket in a log is worthless. Single use is the real protection; this is second.
    stream_ticket_ttl_seconds: int = 30

    # Whether a platform authenticator stands in front. The module MUST NOT assume the layer in front
    # is doing its job: one wrong line in Terraform would leave a ticket factory open to the internet.
    require_authenticated_principal: bool = False

    # Easy Auth authorizes an application, not a route: these two lists are what it cannot say — who
    # is here for `/mcp` and who for the REST contract. Identifiers, not names: a name is a description.
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
