"""Settings, and the one mode switch this module refuses to leave ambiguous: identity off-machine, or password on
loopback, never neither. A tool server's whole setting is optional — unset is a module with no tools."""

from __future__ import annotations

from decimal import Decimal
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Same set market-data's config.py checks against — duplicated here as a requirement, not imported,
# because there is no shared library between modules.
_TLS_REQUIRING_SSLMODES = {"require", "verify-ca", "verify-full"}


class ModelCatalogueEntry(BaseModel):
    """One model this module can hand a turn to. Rates are per 1,000,000 tokens and `Decimal` rather than `float`, since
    summing thousands loses the pennies — and required, so a rateless entry stops the module rather than pricing at zero."""

    id: str
    # What OpenAI is actually asked for, kept separate from `id` because the two need not match: `id`
    # is this module's own stable identifier, outliving a model renamed or retired upstream.
    model: str
    display_name: str
    # Lower is cheaper. An explicit field rather than list order, because order in an env-supplied JSON
    # string is easy to get wrong silently.
    cost_rank: int
    input_rate_per_1m: Decimal
    output_rate_per_1m: Decimal

    @field_validator("id", "model", "display_name")
    @classmethod
    def _not_blank(cls, value: str, info: ValidationInfo) -> str:
        if not value.strip():
            raise ValueError(f"model catalogue entry {info.field_name!s} must not be blank")
        return value.strip()

    @field_validator("input_rate_per_1m", "output_rate_per_1m")
    @classmethod
    def _rate_is_positive(cls, value: Decimal, info: ValidationInfo) -> Decimal:
        if value <= 0:
            raise ValueError(
                f"model catalogue entry rate {info.field_name!s} must be positive, got {value}"
            )
        return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str
    database_user: str | None = None
    azure_client_id: str | None = None
    azure_client_secret: str | None = None
    azure_tenant_id: str | None = None
    # How long this module waits for another process to finish migrating. Sized for the slow case, not
    # a dead one, which releases its lock with its connection. These tables are small; market-data's are not.
    migration_lock_wait_seconds: float = 300.0

    # Required, with no fallback to an ambient credential: OpenAI has no Entra identity to fall back to.
    # A module that started without this would accept a turn and fail after storing the operator's message.
    openai_api_key: str

    models: list[ModelCatalogueEntry] = Field(default_factory=list)
    default_model_id: str

    # Unset means no tools, deliberately: the module answers from the model alone. That is also the state
    # a failed connection degrades to, so the tests walk it.
    market_mcp_url: str | None = None
    # api://<market-mcp-app-id>/.default — the scope this module's managed identity
    # requests a token for. Set only when `market_mcp_url` is not loopback.
    market_mcp_scope: str | None = None
    # Per tool call. The operator is watching a panel, and market-mcp's own ceiling is 10s — a little
    # more here leaves room for its work without turning one slow call into a turn that never ends.
    market_mcp_request_timeout_seconds: float = 15.0

    # No settings for the teams tools, and their absence is the point: that surface is a layer in this
    # process, so there is no address, no token and no timeout. It is also the one that cannot be unconfigured.

    # Unset means what it means for the two above, with the sharpest consequence: the module runs, reads
    # the archive, builds teams, and cannot see a position or send an order.
    trading_mcp_url: str | None = None
    trading_mcp_scope: str | None = None
    # trading-mcp waits on the gateway for up to 30s, and a ceiling below that would time out this side
    # of an order that had already been sent — the one failure shape this must never produce silently.
    trading_mcp_request_timeout_seconds: float = 35.0

    # The third of the three: unset, the module runs and cannot answer what a market prices an event at.
    # Two of its nine tools reach the provider live, which is why the ceiling below is not market-mcp's.
    polymarket_mcp_url: str | None = None
    polymarket_mcp_scope: str | None = None
    # A little past polymarket-data's own ceiling on the provider, for trading-mcp's reason rather than
    # market-mcp's: two of its tools ask Polymarket while the operator waits.
    polymarket_mcp_request_timeout_seconds: float = 35.0

    # The fourth: unset, the module runs and cannot say what was posted. Its tools read one database and
    # reach nothing outward while the operator waits, so the ceiling is market-mcp's rather than the other two's.
    social_mcp_url: str | None = None
    social_mcp_scope: str | None = None
    social_mcp_request_timeout_seconds: float = 15.0

    # The fifth, and the first whose tool does something outside this system. Its ceiling is trading-mcp's
    # number for trading-mcp's reason: a timeout on this side of a message that was already delivered is a
    # notification the operator gets twice, or one this module reports as failed after it arrived.
    telegram_mcp_url: str | None = None
    telegram_mcp_scope: str | None = None
    telegram_mcp_request_timeout_seconds: float = 35.0

    # Mirrors market-data's own field and reasoning: a request without an identity, accepted because this
    # was left off, opens every session in the database — and every call that costs real money.
    require_authenticated_principal: bool = False

    @field_validator("database_url", "openai_api_key")
    @classmethod
    def _not_blank(cls, value: str, info: ValidationInfo) -> str:
        if not value.strip():
            raise ValueError(f"{str(info.field_name).upper()} is set but empty")
        return value.strip()

    @field_validator(
        "database_user",
        "market_mcp_url",
        "market_mcp_scope",
        "trading_mcp_url",
        "trading_mcp_scope",
        "polymarket_mcp_url",
        "polymarket_mcp_scope",
        "social_mcp_url",
        "social_mcp_scope",
        "telegram_mcp_url",
        "telegram_mcp_scope",
    )
    @classmethod
    def _blank_means_unset(cls, value: str | None) -> str | None:
        # `MARKET_MCP_URL=` left in a .env is the same intent as the line being absent: an empty string
        # is not a value, it is a line someone stopped filling.
        if value is None or not value.strip():
            return None
        return value.strip()

    @model_validator(mode="after")
    def _database_mode_is_coherent(self) -> Settings:
        """Same two failures market-data's config.py refuses, duplicated rather than shared — this module
        owns its own database and its own guard on it."""
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
                "loopback — a remote database needs DATABASE_USER and an Entra identity."
            )
        return self

    @model_validator(mode="after")
    def _tool_server_modes_are_coherent(self) -> Settings:
        """The third copy of the rule market-data set for its database: name one mode, or none, never
        both. Run once per server, and every message names the one it is about."""
        self.market_mcp_url = _checked_server(
            "MARKET_MCP", self.market_mcp_url, self.market_mcp_scope
        )
        self.trading_mcp_url = _checked_server(
            "TRADING_MCP", self.trading_mcp_url, self.trading_mcp_scope
        )
        self.polymarket_mcp_url = _checked_server(
            "POLYMARKET_MCP", self.polymarket_mcp_url, self.polymarket_mcp_scope
        )
        self.social_mcp_url = _checked_server(
            "SOCIAL_MCP", self.social_mcp_url, self.social_mcp_scope
        )
        self.telegram_mcp_url = _checked_server(
            "TELEGRAM_MCP", self.telegram_mcp_url, self.telegram_mcp_scope
        )
        return self

    @model_validator(mode="after")
    def _catalogue_is_coherent(self) -> Settings:
        if not self.models:
            raise ValueError(
                "MODELS is empty — the module has no model to offer a session, and "
                "specs/agent-models requires a catalogue a wybierak can be built from."
            )
        ids = [m.id for m in self.models]
        if len(ids) != len(set(ids)):
            raise ValueError(f"MODELS has duplicate model ids: {ids}")
        if self.default_model_id not in ids:
            raise ValueError(
                f"DEFAULT_MODEL_ID {self.default_model_id!r} is not among the configured "
                f"model ids {ids} — a session with no model chosen would have nothing to "
                "fall back to."
            )
        return self


def _checked_server(prefix: str, url: str | None, scope: str | None) -> str | None:
    """One tool server's mode, refused rather than guessed. Returns the URL with any trailing slash
    removed, or `None` for a server this module simply does not have."""
    if url is None:
        if scope is not None:
            raise ValueError(
                f"{prefix}_SCOPE is set but {prefix}_URL is not — a scope names the "
                "audience of a token for a server this module has no address for. Set "
                "the URL, or unset the scope to run without that server's tools."
            )
        return None

    url = url.rstrip("/")
    host = (urlparse(url).hostname or "").lower()
    is_loopback = host == "localhost" or host.startswith("127.") or host == "::1"

    if scope is not None:
        if is_loopback:
            raise ValueError(
                f"{prefix}_SCOPE is set but {prefix}_URL points at loopback ({url!r}) — "
                f"a scope belongs to a remote tool server; unset {prefix}_SCOPE for "
                "local development, or point the URL at the remote instance it names a "
                "token for."
            )
        return url

    if not is_loopback:
        raise ValueError(
            f"{prefix}_URL points at {host!r} with no {prefix}_SCOPE set. Without a "
            "scope this module only reaches a tool server on this machine's loopback — "
            f"a remote one needs {prefix}_SCOPE and the managed identity it is "
            "requested for."
        )
    return url
