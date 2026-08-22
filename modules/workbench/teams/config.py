"""Settings, and the mode switches this module refuses to leave ambiguous.

The database follows the rule market-data's and agent's `config.py` set for their own:
`database_user` set → identity, off-machine; unset → password, loopback only. A
configuration naming neither or both is rejected at startup rather than guessed at
(specs/teams-database-connection, "Moduł nie dzieli bazy z innym modułem" — every module
owning a database duplicates this check rather than share it).

The model provider has no such switch, because there is nothing to switch between:
OpenAI is not in Entra, so a managed identity has nobody to present a token to and
`openai_api_key` is the only credential either shape can use. Local and production
differ only in where the value comes from — `.env` there, a Key Vault reference here
(infra/key-vault.tf, secret `teams-openai-api-key` — a key of this module's own, not
shared with `agent`, so the cost of these experiments shows up on its own line).

The tool server has the database's shape rather than the provider's:
`market_mcp_scope` set → the server is off this machine and a token for that scope is
what proves this module to it; unset → `market_mcp_url` MUST point at loopback. It
differs from the database in one way that matters — the whole setting is optional. An
unset `market_mcp_url` is not a misconfiguration: a team whose agents carry no tools
never needs one (specs/teams-tool-access).

Unlike agent's catalogue, there is no `default_model_id` here: a team's definition MUST
name a model for every agent it holds (specs/teams-models, "Model wybiera się osobno dla
każdego agenta") — there is no session that falls back to a module-wide default, because
there is no session, only a revision that either names a model or is refused at the
point it is saved.

Refusing to build the settings leaves nothing running to misuse.
"""

from __future__ import annotations

from decimal import Decimal
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Same set market-data's and agent's config.py check against — "Połączenie z bazą jest
# szyfrowane" is duplicated here as a requirement (specs/teams-database-connection), not
# imported, because there is no shared library between modules.
_TLS_REQUIRING_SSLMODES = {"require", "verify-ca", "verify-full"}


class ModelCatalogueEntry(BaseModel):
    """One model an agent in a team can be assigned.

    Rates are per 1,000,000 tokens — the unit every provider advertises, so a rate copied
    from a pricing page needs no arithmetic on the way in and none on the way out to the
    operator. `Decimal` rather than `float`: a run costs a fraction of a cent across
    several agents, and summing thousands of `float`s loses the pennies the usage ledger
    exists to get right.

    Required, not defaulted — a model entry without a rate must fail to *parse*, which
    is what keeps the module from starting rather than starting and pricing a run as
    free (specs/teams-models, "Model spoza katalogu jest odmową, nie podmianą").
    """

    id: str
    # What OpenAI is actually asked for. Kept separate from `id` because the two need
    # not match: `id` is this module's own stable identifier, carried in every team
    # revision and usage row, and outliving a model renamed or retired upstream.
    model: str
    display_name: str
    # Lower is cheaper. An explicit field rather than list order, because list order in
    # an env-supplied JSON string is easy to get wrong silently; a wybierak sorts by
    # this and a config typo in the order shows up as a wrong number, not a swapped row.
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

    # --- this module's own storage — same switch as market-data/config.py and
    # agent/config.py ---
    database_url: str
    database_user: str | None = None
    azure_client_id: str | None = None
    azure_client_secret: str | None = None
    azure_tenant_id: str | None = None
    # How long this module waits for another process to finish migrating before it gives
    # up and refuses to start. Sized for the slow case — a migration running ahead of us —
    # not for a dead one, which releases its lock with its connection. This module's
    # tables are small, the same reasoning agent's own wait carries.
    migration_lock_wait_seconds: float = 300.0

    # --- OpenAI, this module's only model provider ---
    #
    # Required, with no fallback to an ambient credential: unlike the database, OpenAI
    # has no Entra identity to fall back *to*. A module that started without this would
    # accept a run and fail on the first call, after the operator's team was already
    # committed to a revision.
    openai_api_key: str

    # --- the models a team's agents can be assigned ---
    #
    # No `default_model_id`: every agent in a saved revision MUST name its own model, so
    # there is nothing here to fall back to (specs/teams-models).
    models: list[ModelCatalogueEntry] = Field(default_factory=list)

    # --- market-mcp, the read tool server ---
    #
    # Unset means no tools, deliberately: a team whose agents carry no assigned tools
    # never reaches this at all, and a team that does is refused at run time rather than
    # left to guess (specs/teams-tool-access, "Brak serwera narzędzi zatrzymuje przebieg,
    # zamiast pozwolić zespołowi zgadywać").
    market_mcp_url: str | None = None
    # api://<market-mcp-app-id>/.default — the scope this module's managed identity
    # requests a token for. Set only when `market_mcp_url` is not loopback.
    market_mcp_scope: str | None = None
    # Per tool call. The operator is watching a panel while this runs, and market-mcp's
    # own ceiling on reaching the archive is 10s — a little more than that here leaves
    # room for its own work without turning one slow call into a run that never ends.
    market_mcp_request_timeout_seconds: float = 15.0

    # --- trading-mcp, the write tool server ---
    #
    # Same shape as market-mcp's three settings above, and independently optional: a
    # team whose agents carry no write tool never touches this one even when it is
    # unreachable (specs/teams-tool-access, "Nieosiągalny jest tylko serwer, z którego
    # nikt nic nie ma").
    trading_mcp_url: str | None = None
    trading_mcp_scope: str | None = None
    # A little past trading-mcp's own ceiling on capital-gateway (30s) — a write that
    # takes the gateway's full worst case still has to read here as "slow", not as
    # this module's own timeout firing first.
    trading_mcp_request_timeout_seconds: float = 35.0

    # --- polymarket-data, the third tool server ---
    #
    # Same shape and the same independence as the two above. Its ceiling is trading-mcp's
    # number for trading-mcp's reason rather than market-mcp's: two of its tools ask the
    # provider live (30s there, `polymarket_data/provider.py`), so a lower ceiling here
    # would fire on a call still being answered.
    polymarket_mcp_url: str | None = None
    polymarket_mcp_scope: str | None = None
    polymarket_mcp_request_timeout_seconds: float = 35.0

    # --- how long one run may take ---
    #
    # A ceiling on the whole run, not on one agent: several agents work in it, some at the
    # same time, and the thing an operator waits on is the run (specs/teams-runs,
    # "Przebieg ma skończony czas i daje się przerwać"). Fifteen minutes is generous for a
    # team of a handful of roles reading the archive, and short enough that a run nobody
    # is watching cannot bill through the night.
    #
    # A setting rather than a constant, unlike the per-agent round ceiling: how long is
    # too long depends on how big a team the operator built, while "how many times may one
    # agent reach for a tool" is a safety property that should not be raised because it is
    # inconvenient (`runner/loop.py`, ROUND_CEILING).
    run_timeout_seconds: float = 900.0

    # --- who may call this module from a browser ---
    #
    # Mirrors market-data's and agent's own field and reasoning: a request without an
    # identity, accepted because this was left off, opens every team's catalogue and
    # every run's trace in the database to whoever finds the address — and every call to
    # a model that costs real money with it. Off locally, where nothing stands in front
    # and there is no identity to have.
    require_authenticated_principal: bool = False

    # --- the module's own clock ---
    #
    # A schedule or trigger fires from a task in this process's own `lifespan`, not from
    # anything in Azure (design.md, "Zegar w procesie modułu, nie w Azure") — a timer
    # calling in from outside would need its own Entra registration to get past Easy
    # Auth, and would put the schedule in Terraform, which is to say back in the
    # operator's hands.
    #
    # The lever that turns it off without a redeploy — clearing this and restarting
    # leaves every schedule and trigger exactly where it was, and a run started by hand
    # still works (specs/teams-schedules, "Budzenie wyłączone ustawieniem").
    scheduler_enabled: bool = True
    # How often the clock wakes to look for a due schedule or trigger. Fifteen seconds:
    # short enough that a five-minute schedule fires close to on time, long enough that
    # an idle catalogue costs one cheap query a wake rather than a busy loop.
    scheduler_poll_interval_seconds: float = 15.0
    # How many *consecutive* failed runs a schedule or trigger tolerates before it
    # disables itself (specs/teams-schedules, "Harmonogram po serii nieudanych
    # przebiegów wyłącza się sam"). Three: enough that one bad model response is not
    # mistaken for a broken schedule, few enough that a genuinely broken one does not
    # bill through the night before an operator notices.
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
    )
    @classmethod
    def _blank_means_unset(cls, value: str | None) -> str | None:
        # `MARKET_MCP_URL=` left in a .env is the same intent as the line being absent,
        # and the same reading the database's own user field has had since agent's
        # config.py was written: an empty string is not a value, it is a line someone
        # stopped filling.
        if value is None or not value.strip():
            return None
        return value.strip()

    @model_validator(mode="after")
    def _database_mode_is_coherent(self) -> Settings:
        """Same two failures market-data's and agent's config.py refuse, duplicated
        rather than shared — this module owns its own database and its own guard on it
        (specs/teams-database-connection, "Moduł nie dzieli bazy z innym modułem")."""
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
        """The same rule market-data set for its database and market-mcp set for its
        archive, and agent set for its own tool server: name one mode, or none, never
        both — checked independently for each configured tool server, so an operator
        fixing one does not have to guess which of them a bare error names
        (specs/teams-tool-access, "Tryb połączenia z serwerem narzędzi jest wybrany
        jednoznacznie", "Niespójność dotyczy drugiego serwera")."""
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
