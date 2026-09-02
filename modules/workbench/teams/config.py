"""Settings, and the mode switches this module refuses to leave ambiguous: identity off-machine or password on loopback,
never neither. There is no default model — a revision names one per agent or is refused at save."""

from __future__ import annotations

from decimal import Decimal
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Same set market-data's and agent's config.py check against — duplicated here as a requirement, not
# imported, because there is no shared library between modules.
_TLS_REQUIRING_SSLMODES = {"require", "verify-ca", "verify-full"}


class ModelCatalogueEntry(BaseModel):
    """One model an agent can be assigned. Rates are per 1,000,000 tokens and `Decimal` rather than `float`, because a run
    costs a fraction of a cent across several agents — and required, so a rateless entry stops the module starting."""

    id: str
    # What OpenAI is actually asked for, kept separate from `id` because the two need not match: `id` is
    # this module's own stable identifier, outliving a model renamed or retired upstream.
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
    # How long this module waits for another process to finish migrating. Sized for the slow case, not a
    # dead one, which releases its lock with its connection.
    migration_lock_wait_seconds: float = 300.0

    # Required, with no fallback to an ambient credential: OpenAI has no Entra identity to fall back to. A
    # module that started without this would fail on the first call, after the team was already committed.
    openai_api_key: str

    # No `default_model_id`: every agent in a saved revision MUST name its own model, so
    # there is nothing here to fall back to (specs/teams-models).
    models: list[ModelCatalogueEntry] = Field(default_factory=list)

    # Unset means no tools, deliberately: a team whose agents carry none never reaches this, and one that
    # does is refused at run time rather than left to guess.
    market_mcp_url: str | None = None
    # api://<market-mcp-app-id>/.default — the scope this module's managed identity
    # requests a token for. Set only when `market_mcp_url` is not loopback.
    market_mcp_scope: str | None = None
    # Per tool call. The operator is watching a panel, and market-mcp's own ceiling is 10s — a little more
    # here leaves room for its work without turning one slow call into a run that never ends.
    market_mcp_request_timeout_seconds: float = 15.0

    # Same shape as market-mcp's three above, and independently optional: a team whose agents carry no
    # write tool never touches this one even when it is unreachable.
    trading_mcp_url: str | None = None
    trading_mcp_scope: str | None = None
    # A little past trading-mcp's own ceiling on capital-gateway — a write that takes the gateway's full
    # worst case still has to read here as "slow", not as this module's own timeout firing first.
    trading_mcp_request_timeout_seconds: float = 35.0

    # Same shape and independence as the two above. Its ceiling is trading-mcp's number for trading-mcp's
    # reason: two of its tools ask the provider live, so a lower one would fire mid-answer.
    polymarket_mcp_url: str | None = None
    polymarket_mcp_scope: str | None = None
    polymarket_mcp_request_timeout_seconds: float = 35.0

    # The fourth, same shape and independence. Its ceiling is market-mcp's number for market-mcp's reason:
    # every one of its tools reads this system's own database and reaches nothing outward.
    social_mcp_url: str | None = None
    social_mcp_scope: str | None = None
    social_mcp_request_timeout_seconds: float = 15.0

    # The fifth, and the only one whose tool acts outside this system. Its ceiling is trading-mcp's number
    # for trading-mcp's reason: a timeout on this side of a message already delivered is a notification
    # sent twice, or one reported as failed after it arrived.
    telegram_mcp_url: str | None = None
    telegram_mcp_scope: str | None = None
    telegram_mcp_request_timeout_seconds: float = 35.0

    # The sixth, and the one the clock reads: `pending_setups` is the number a trigger compares against its
    # threshold, over the same session a woken team then reads the decision from. One database, no upstream —
    # social-mcp's ceiling.
    strategy_mcp_url: str | None = None
    strategy_mcp_scope: str | None = None
    strategy_mcp_request_timeout_seconds: float = 15.0

    # A ceiling on the whole run, not on one agent: the thing an operator waits on is the run. A setting
    # rather than a constant, unlike the per-agent round ceiling, which is a safety property.
    run_timeout_seconds: float = 900.0

    # Mirrors market-data's and agent's own field and reasoning: a request without an identity, accepted
    # because this was left off, opens every team's catalogue and every run's trace to whoever finds it.
    require_authenticated_principal: bool = False

    # A schedule fires from a task in this process's own lifespan, not from anything in Azure: a timer
    # calling in would need its own registration and would put the schedule back in Terraform.
    scheduler_enabled: bool = True
    # How often the clock wakes to look for a due schedule. Fifteen seconds: close enough to on time for a
    # five-minute schedule, long enough that an idle catalogue costs one cheap query a wake.
    scheduler_poll_interval_seconds: float = 15.0
    # How many *consecutive* failed runs a schedule tolerates before disabling itself. Three: enough that
    # one bad model response is not a broken schedule, few enough that a broken one is caught the same night.
    scheduler_failure_threshold: int = 3

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
        "strategy_mcp_url",
        "strategy_mcp_scope",
    )
    @classmethod
    def _blank_means_unset(cls, value: str | None) -> str | None:
        # `MARKET_MCP_URL=` left in a .env is the same intent as the line being absent: an empty string is
        # not a value, it is a line someone stopped filling.
        if value is None or not value.strip():
            return None
        return value.strip()

    @model_validator(mode="after")
    def _database_mode_is_coherent(self) -> Settings:
        """Same two failures market-data's and agent's config.py refuse, duplicated rather than shared —
        this module owns its own database and its own guard on it."""
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
        """The same rule every module here sets for a mode: name one, or none, never both — checked
        independently per configured server, so an operator fixing one need not guess which a bare error names."""
        self.market_mcp_url = self._coherent_tool_server_url(
            url=self.market_mcp_url, scope=self.market_mcp_scope, env_prefix="MARKET_MCP"
        )
        self.trading_mcp_url = self._coherent_tool_server_url(
            url=self.trading_mcp_url, scope=self.trading_mcp_scope, env_prefix="TRADING_MCP"
        )
        self.polymarket_mcp_url = self._coherent_tool_server_url(
            url=self.polymarket_mcp_url,
            scope=self.polymarket_mcp_scope,
            env_prefix="POLYMARKET_MCP",
        )
        self.social_mcp_url = self._coherent_tool_server_url(
            url=self.social_mcp_url, scope=self.social_mcp_scope, env_prefix="SOCIAL_MCP"
        )
        self.telegram_mcp_url = self._coherent_tool_server_url(
            url=self.telegram_mcp_url, scope=self.telegram_mcp_scope, env_prefix="TELEGRAM_MCP"
        )
        self.strategy_mcp_url = self._coherent_tool_server_url(
            url=self.strategy_mcp_url, scope=self.strategy_mcp_scope, env_prefix="STRATEGY_MCP"
        )
        return self

    @staticmethod
    def _coherent_tool_server_url(*, url: str | None, scope: str | None, env_prefix: str) -> str | None:
        if url is None:
            if scope is not None:
                raise ValueError(
                    f"{env_prefix}_SCOPE is set but {env_prefix}_URL is not — a scope "
                    "names the audience of a token for a server this module has no "
                    f"address for. Set the URL, or unset {env_prefix}_SCOPE to run "
                    "without this tool server configured."
                )
            return None

        url = url.rstrip("/")
        host = (urlparse(url).hostname or "").lower()
        is_loopback = host == "localhost" or host.startswith("127.") or host == "::1"

        if scope is not None:
            if is_loopback:
                raise ValueError(
                    f"{env_prefix}_SCOPE is set but {env_prefix}_URL points at loopback "
                    f"({url!r}) — a scope belongs to a remote tool server; unset "
                    f"{env_prefix}_SCOPE for local development, or point the URL at the "
                    "remote instance it names a token for."
                )
            return url

        if not is_loopback:
            raise ValueError(
                f"{env_prefix}_URL points at {host!r} with no {env_prefix}_SCOPE set. "
                "Without a scope this module only reaches a tool server on this "
                f"machine's loopback — a remote one needs {env_prefix}_SCOPE and the "
                "managed identity it is requested for."
            )
        return url

    @model_validator(mode="after")
    def _catalogue_is_coherent(self) -> Settings:
        if not self.models:
            raise ValueError(
                "MODELS is empty — the module has no model an agent could be assigned, "
                "and specs/teams-models requires a catalogue a wybierak can be built "
                "from."
            )
        ids = [m.id for m in self.models]
        if len(ids) != len(set(ids)):
            raise ValueError(f"MODELS has duplicate model ids: {ids}")
        return self

    @field_validator("scheduler_poll_interval_seconds")
    @classmethod
    def _poll_interval_is_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError(f"SCHEDULER_POLL_INTERVAL_SECONDS must be positive, got {value}")
        return value

    @field_validator("scheduler_failure_threshold")
    @classmethod
    def _failure_threshold_is_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError(f"SCHEDULER_FAILURE_THRESHOLD must be positive, got {value}")
        return value
