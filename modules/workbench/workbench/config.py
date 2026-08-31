"""The one place this process reads its environment. What stays doubled carries a prefix and is doubled on purpose:
two schemas, two OpenAI keys so the experiments bill on their own line, and two catalogues."""

from __future__ import annotations

from pydantic import Field, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from agent.config import ModelCatalogueEntry as AgentModelCatalogueEntry
from agent.config import Settings as AgentSettings
from teams.config import ModelCatalogueEntry as TeamsModelCatalogueEntry
from teams.config import Settings as TeamsSettings


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # One `DATABASE_USER` for both, a consequence of one App Service rather than a simplification: the process
    # presents one identity, and that role has to exist in both databases — the one operator step this change carries.
    agent_database_url: str
    teams_database_url: str
    database_user: str | None = None
    azure_client_id: str | None = None
    azure_client_secret: str | None = None
    azure_tenant_id: str | None = None
    # How long a starting process waits for another to finish migrating before it gives up. One value for both chains:
    # they are the same size of small, and neither is market-data's candle table.
    migration_lock_wait_seconds: float = 300.0

    agent_openai_api_key: str
    teams_openai_api_key: str

    agent_models: list[AgentModelCatalogueEntry] = Field(default_factory=list)
    agent_default_model_id: str
    teams_models: list[TeamsModelCatalogueEntry] = Field(default_factory=list)

    # One address for one archive. Unset means neither surface has archive tools, which is
    # a supported state for both and the state each was in before the setting existed.
    market_mcp_url: str | None = None
    market_mcp_scope: str | None = None
    market_mcp_request_timeout_seconds: float = 15.0

    trading_mcp_url: str | None = None
    trading_mcp_scope: str | None = None
    trading_mcp_request_timeout_seconds: float = 35.0

    # The third pair, read by both surfaces and optional on its own: unset means neither can say what a market prices
    # an event at, which is the state both were in before that module existed.
    polymarket_mcp_url: str | None = None
    polymarket_mcp_scope: str | None = None
    polymarket_mcp_request_timeout_seconds: float = 35.0

    # The fourth pair, same shape as the three above: unset means neither surface can say what was posted.
    # Its tools read one database and reach nothing outward, so the ceiling is the archive's, not the provider's.
    social_mcp_url: str | None = None
    social_mcp_scope: str | None = None
    social_mcp_request_timeout_seconds: float = 15.0

    # No `TEAMS_MCP_*`: the teams tools are a layer in this process now, so a `.env` from before this change carries
    # three settings that are read by nothing.

    run_timeout_seconds: float = 900.0
    scheduler_enabled: bool = True
    scheduler_poll_interval_seconds: float = 15.0
    scheduler_failure_threshold: int = 3

    require_authenticated_principal: bool = False

    @field_validator(
        "agent_database_url",
        "teams_database_url",
        "agent_openai_api_key",
        "teams_openai_api_key",
    )
    @classmethod
    def _not_blank(cls, value: str, info: ValidationInfo) -> str:
        # Named per surface rather than as "DATABASE_URL", because there are two of each and a message that does not
        # say which sends the reader to the wrong line of the same file.
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
    )
    @classmethod
    def _blank_means_unset(cls, value: str | None) -> str | None:
        # `MARKET_MCP_URL=` left in a .env is the same intent as the line being absent. Both surfaces' own settings say
        # this too; it has to happen here as well, because what reaches them is what this class hands over.
        if value is None or not value.strip():
            return None
        return value.strip()

    def for_conversation(self) -> AgentSettings:
        """The conversation surface's own settings, with every one of its validators run. Every field is
        passed, so nothing falls back to the environment and a stray `DATABASE_URL` cannot shadow it."""
        return AgentSettings(
            database_url=self.agent_database_url,
            database_user=self.database_user,
            azure_client_id=self.azure_client_id,
            azure_client_secret=self.azure_client_secret,
            azure_tenant_id=self.azure_tenant_id,
            migration_lock_wait_seconds=self.migration_lock_wait_seconds,
            openai_api_key=self.agent_openai_api_key,
            models=self.agent_models,
            default_model_id=self.agent_default_model_id,
            market_mcp_url=self.market_mcp_url,
            market_mcp_scope=self.market_mcp_scope,
            market_mcp_request_timeout_seconds=self.market_mcp_request_timeout_seconds,
            # No teams server: those tools are reached in this process, and the field they
            # used to fill is gone from `agent.config.Settings` with them.
            trading_mcp_url=self.trading_mcp_url,
            trading_mcp_scope=self.trading_mcp_scope,
            trading_mcp_request_timeout_seconds=self.trading_mcp_request_timeout_seconds,
            polymarket_mcp_url=self.polymarket_mcp_url,
            polymarket_mcp_scope=self.polymarket_mcp_scope,
            polymarket_mcp_request_timeout_seconds=self.polymarket_mcp_request_timeout_seconds,
            social_mcp_url=self.social_mcp_url,
            social_mcp_scope=self.social_mcp_scope,
            social_mcp_request_timeout_seconds=self.social_mcp_request_timeout_seconds,
            require_authenticated_principal=self.require_authenticated_principal,
        )

    def for_teams(self) -> TeamsSettings:
        """The teams surface's own settings — same treatment, its own validators."""
        return TeamsSettings(
            database_url=self.teams_database_url,
            database_user=self.database_user,
            azure_client_id=self.azure_client_id,
            azure_client_secret=self.azure_client_secret,
            azure_tenant_id=self.azure_tenant_id,
            migration_lock_wait_seconds=self.migration_lock_wait_seconds,
            openai_api_key=self.teams_openai_api_key,
            models=self.teams_models,
            market_mcp_url=self.market_mcp_url,
            market_mcp_scope=self.market_mcp_scope,
            market_mcp_request_timeout_seconds=self.market_mcp_request_timeout_seconds,
            trading_mcp_url=self.trading_mcp_url,
            trading_mcp_scope=self.trading_mcp_scope,
            trading_mcp_request_timeout_seconds=self.trading_mcp_request_timeout_seconds,
            polymarket_mcp_url=self.polymarket_mcp_url,
            polymarket_mcp_scope=self.polymarket_mcp_scope,
            polymarket_mcp_request_timeout_seconds=self.polymarket_mcp_request_timeout_seconds,
            social_mcp_url=self.social_mcp_url,
            social_mcp_scope=self.social_mcp_scope,
            social_mcp_request_timeout_seconds=self.social_mcp_request_timeout_seconds,
            run_timeout_seconds=self.run_timeout_seconds,
            require_authenticated_principal=self.require_authenticated_principal,
            scheduler_enabled=self.scheduler_enabled,
            scheduler_poll_interval_seconds=self.scheduler_poll_interval_seconds,
            scheduler_failure_threshold=self.scheduler_failure_threshold,
        )
