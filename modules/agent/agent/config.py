"""Settings, and the one mode switch this module refuses to leave ambiguous.

The database follows the rule market-data's `config.py` set for its own: `database_user`
set → identity, off-machine; unset → password, loopback only. A configuration naming
neither or both is rejected at startup rather than guessed at (design.md, "Moduł nie
dzieli bazy z innym modułem" — the two modules duplicate this check rather than share
it).

The model provider has no such switch, because there is nothing to switch between:
OpenAI is not in Entra, so a managed identity has nobody to present a token to and
`openai_api_key` is the only credential either shape can use (design.md, "Wobec OpenAI:
klucz, i tylko klucz"). Local and production differ only in where the value comes from —
`.env` there, a Key Vault reference here (infra/key-vault.tf).

The tool server has the database's shape rather than the provider's: `market_mcp_scope`
set → the server is off this machine and a token for that scope is what proves this
module to it; unset → `market_mcp_url` MUST point at loopback. It differs from the
database in one way that matters — the whole setting is optional. An unset
`market_mcp_url` is not a misconfiguration but a module with no tools, which is what
this module was until this change and what it falls back to when the server is down
(specs/agent-tool-access, "Brak serwera narzędzi nie odbiera agentowi mowy").

Refusing to build the settings leaves nothing running to misuse.
"""

from __future__ import annotations

from decimal import Decimal
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Same set market-data's config.py checks against — "Połączenie z bazą jest szyfrowane"
# is duplicated here as a requirement (specs/agent-database-connection), not imported,
# because there is no shared library between modules.
_TLS_REQUIRING_SSLMODES = {"require", "verify-ca", "verify-full"}


class ModelCatalogueEntry(BaseModel):
    """One model this module can hand a turn to.

    Rates are per 1,000,000 tokens — the unit every provider advertises, so a rate copied
    from a pricing page needs no arithmetic on the way in and none on the way out to the
    operator. `Decimal` rather than `float`: a turn costs a fraction of a cent, and
    summing thousands of `float`s loses the pennies the usage ledger exists to get right
    (design.md, "Cennik jest konfiguracją, stawka jest przepisywana na wiersz").

    Required, not defaulted — a model entry without a rate must fail to *parse*, which
    is what keeps the module from starting rather than starting and pricing a turn as
    free (specs/agent-models, "Model spoza katalogu jest odmową, nie podmianą").
    """

    id: str
    # What OpenAI is actually asked for. Kept separate from `id` because the two need
    # not match: `id` is this module's own stable identifier, carried in every session
    # and usage row, and outliving a model renamed or retired upstream.
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

    # --- this module's own storage — same switch as market-data/config.py ---
    database_url: str
    database_user: str | None = None
    azure_client_id: str | None = None
    azure_client_secret: str | None = None
    azure_tenant_id: str | None = None

    # --- OpenAI, this module's only model provider ---
    #
    # Required, with no fallback to an ambient credential: unlike the database, OpenAI
    # has no Entra identity to fall back *to*. A module that started without this would
    # accept a turn and fail on the call, after the operator's message was already
    # stored.
    openai_api_key: str

    # --- the models this module offers, and which one a session gets by default ---
    models: list[ModelCatalogueEntry] = Field(default_factory=list)
    default_model_id: str

    # --- market-mcp, this module's only tool server ---
    #
    # Unset means no tools, deliberately: the module answers from the model alone, the
    # way it did before this setting existed. That is also the state a failed connection
    # degrades to, so it is a path the tests exercise rather than a corner nobody has
    # been down.
    market_mcp_url: str | None = None
    # api://<market-mcp-app-id>/.default — the scope this module's managed identity
    # requests a token for. Set only when `market_mcp_url` is not loopback.
    market_mcp_scope: str | None = None
    # Per tool call. The operator is watching a panel while this runs, and market-mcp's
    # own ceiling on reaching the archive is 10s — a little more than that here leaves
    # room for its own work without turning one slow call into a turn that never ends.
    market_mcp_request_timeout_seconds: float = 15.0

    # --- who may call this module from a browser ---
    #
    # Mirrors market-data's own field and its own reasoning: a request without an
    # identity, accepted because this was left off, opens every session in the database
    # to whoever finds the address — and every call to a model that costs real money
    # with it. Off locally, where nothing stands in front and there is no identity to
    # have.
    require_authenticated_principal: bool = False

    @field_validator("database_url", "openai_api_key")
    @classmethod
    def _not_blank(cls, value: str, info: ValidationInfo) -> str:
        if not value.strip():
            raise ValueError(f"{str(info.field_name).upper()} is set but empty")
        return value.strip()

    @field_validator("database_user", "market_mcp_url", "market_mcp_scope")
    @classmethod
    def _blank_means_unset(cls, value: str | None) -> str | None:
        # `MARKET_MCP_URL=` left in a .env is the same intent as the line being absent,
        # and the same reading the database's own user field has had since it was
        # written: an empty string is not a value, it is a line someone stopped filling.
        if value is None or not value.strip():
            return None
        return value.strip()

    @model_validator(mode="after")
    def _database_mode_is_coherent(self) -> Settings:
        """Same two failures market-data's config.py refuses, duplicated rather than
        shared — this module owns its own database and its own guard on it
        (specs/agent-database-connection, "Moduł nie dzieli bazy z innym modułem")."""
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
    def _tool_server_mode_is_coherent(self) -> Settings:
        """The third copy of the rule market-data set for its database and market-mcp
        set for its archive: name one mode, or none, never both
        (specs/agent-tool-access, "Tryb połączenia z serwerem narzędzi jest wybrany
        jednoznacznie")."""
        if self.market_mcp_url is None:
            if self.market_mcp_scope is not None:
                raise ValueError(
                    "MARKET_MCP_SCOPE is set but MARKET_MCP_URL is not — a scope names "
                    "the audience of a token for a server this module has no address "
                    "for. Set the URL, or unset the scope to run without tools."
                )
            return self

        self.market_mcp_url = self.market_mcp_url.rstrip("/")
        host = (urlparse(self.market_mcp_url).hostname or "").lower()
        is_loopback = host == "localhost" or host.startswith("127.") or host == "::1"

        if self.market_mcp_scope is not None:
            if is_loopback:
                raise ValueError(
                    f"MARKET_MCP_SCOPE is set but MARKET_MCP_URL points at loopback "
                    f"({self.market_mcp_url!r}) — a scope belongs to a remote tool "
                    "server; unset MARKET_MCP_SCOPE for local development, or point "
                    "the URL at the remote instance it names a token for."
                )
            return self

        if not is_loopback:
            raise ValueError(
                f"MARKET_MCP_URL points at {host!r} with no MARKET_MCP_SCOPE set. "
                "Without a scope this module only reaches a tool server on this "
                "machine's loopback — a remote one needs MARKET_MCP_SCOPE and the "
                "managed identity it is requested for."
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
