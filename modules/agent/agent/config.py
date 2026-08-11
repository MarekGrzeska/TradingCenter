"""Settings, and the two mode switches this module refuses to leave ambiguous.

Two things here pick between a local shape and a remote one, and both follow the same
rule market-data's `config.py` set for its database: **exactly one** of a pair of
settings selects the mode, and a configuration naming neither or both is rejected at
startup rather than guessed at.

  database         `database_user` set → identity, off-machine. Unset → password,
                    loopback only. Mirrors market-data's own switch (design.md, "Moduł
                    nie dzieli bazy z innym modułem" — the two modules duplicate this
                    check rather than share it).

  model provider   `azure_openai_api_key` set → key, local. `azure_openai_use_managed_
                    identity` true → managed identity, production. A key *and* the flag
                    together do not say which of them actually pays (design.md, "Wobec
                    Azure OpenAI: tożsamość zarządzana, lokalnie klucz").

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

    Rates are per 1000 tokens, `Decimal` rather than `float`: a turn costs a fraction of
    a cent, and summing thousands of `float`s loses the pennies the usage ledger exists
    to get right (design.md, "Cennik jest konfiguracją, stawka jest przepisywana na
    wiersz").

    Required, not defaulted — a model entry without a rate must fail to *parse*, which
    is what keeps the module from starting rather than starting and pricing a turn as
    free (specs/agent-models, "Model spoza katalogu jest odmową, nie podmianą").
    """

    id: str
    # The name this deployment is known by in Azure OpenAI — what a call actually
    # addresses. Kept separate from `id` because the two need not match: `id` is this
    # module's own stable identifier, carried in every session and usage row, and
    # outliving a deployment renamed or moved to a different region.
    deployment: str
    display_name: str
    # Lower is cheaper. An explicit field rather than list order, because list order in
    # an env-supplied JSON string is easy to get wrong silently; a wybierak sorts by
    # this and a config typo in the order shows up as a wrong number, not a swapped row.
    cost_rank: int
    input_rate_per_1k: Decimal
    output_rate_per_1k: Decimal

    @field_validator("id", "deployment", "display_name")
    @classmethod
    def _not_blank(cls, value: str, info: ValidationInfo) -> str:
        if not value.strip():
            raise ValueError(f"model catalogue entry {info.field_name!s} must not be blank")
        return value.strip()

    @field_validator("input_rate_per_1k", "output_rate_per_1k")
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

    # --- Azure OpenAI, this module's only model provider ---
    azure_openai_endpoint: str
    # No default: Azure OpenAI's REST surface is versioned by a query parameter that
    # moves independently of this module's releases, and a guessed date here is a
    # deployment that answers 400 for a reason nothing in this file explains.
    azure_openai_api_version: str
    azure_openai_api_key: str | None = None
    azure_openai_use_managed_identity: bool = False

    # --- the models this module offers, and which one a session gets by default ---
    models: list[ModelCatalogueEntry] = Field(default_factory=list)
    default_model_id: str

    # --- who may call this module from a browser ---
    #
    # Mirrors market-data's own field and its own reasoning: a request without an
    # identity, accepted because this was left off, opens every session in the database
    # to whoever finds the address — and every call to a model that costs real money
    # with it. Off locally, where nothing stands in front and there is no identity to
    # have.
    require_authenticated_principal: bool = False

    @field_validator("database_url", "azure_openai_endpoint", "azure_openai_api_version")
    @classmethod
    def _not_blank(cls, value: str, info: ValidationInfo) -> str:
        if not value.strip():
            raise ValueError(f"{str(info.field_name).upper()} is set but empty")
        return value.strip()

    @field_validator("database_user")
    @classmethod
    def _blank_database_user_means_unset(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return value.strip()

    @field_validator("azure_openai_api_key")
    @classmethod
    def _blank_api_key_means_unset(cls, value: str | None) -> str | None:
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
    def _provider_mode_is_coherent(self) -> Settings:
        has_key = self.azure_openai_api_key is not None
        if has_key == self.azure_openai_use_managed_identity:
            if has_key:
                raise ValueError(
                    "AZURE_OPENAI_API_KEY is set and AZURE_OPENAI_USE_MANAGED_IDENTITY is "
                    "true — set exactly one, so which of them actually authenticates a "
                    "call is never a guess."
                )
            raise ValueError(
                "Neither AZURE_OPENAI_API_KEY nor AZURE_OPENAI_USE_MANAGED_IDENTITY is "
                "set. Local development sets the key; a deployed instance sets the flag "
                "and authenticates with its managed identity."
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
