"""Settings, and the one switch that decides how this module reaches `teams`.

The pattern is the fourth copy of one set by `market_data/config.py` and repeated by
`agent`, `market-mcp` and `trading-mcp`: exactly one setting names the mode, and a
configuration that leaves it ambiguous is rejected at startup rather than guessed at.

  upstream access   `teams_scope` set → `teams` is off this machine, and a token for
                     that scope is what proves *this module* to it. Unset →
                     `teams_url` MUST point at loopback (specs/teams-mcp-upstream-access,
                     "Tryb połączenia jest wybrany jednoznacznie, nie zgadnięty").

**That scope authenticates the module, not the operator, and the two are not
interchangeable.** Every tool here acts in the name of the person who asked for it, and
their identity arrives per call, carried from `agent` (`operator.py`). A module reaching
`teams` on its own identity alone would create teams nobody can see — see design.md, D2.

Refusing to build the settings leaves nothing running to misuse.
"""

from __future__ import annotations

from urllib.parse import urlparse

from pydantic import ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def points_at_loopback(url: str) -> bool:
    """Whether this address is on the machine the module runs on.

    Out of the upstream-mode validator and into its own function because a second reader
    needs the same fact: `operator_identity_optional` below asks it about `teams_url` to
    decide whether an operator's identity could have existed at all.
    """
    host = (urlparse(url).hostname or "").lower()
    return host == "localhost" or host.startswith("127.") or host == "::1"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- teams, this module's only upstream ---
    teams_url: str = "http://127.0.0.1:8050"
    # api://<teams-app-id>/.default — the scope this module's managed identity requests
    # a token for. Set only when `teams_url` is not loopback.
    teams_scope: str | None = None
    # Just past the slowest thing one tool call asks for. Starting a run answers as soon
    # as the run row exists — `teams` does not hold the request open for the run itself
    # — so this covers a catalogue write, not a team working.
    teams_request_timeout_seconds: float = 30.0

    # --- this module's own HTTP surface, for the streamable-http transport ---
    teams_mcp_port: int = 8070
    # Loopback by default; the container overrides it (`Dockerfile`, ENV). It matters
    # locally: `require_authenticated_principal` is off on a desk, so binding every
    # interface would publish tools that create and run teams to whatever network the
    # machine is on.
    teams_mcp_host: str = "127.0.0.1"

    # Whether a platform authenticator (Easy Auth) stands in front of this module — the
    # module does not take on trust that the layer in front is configured correctly
    # (specs/teams-mcp-transport, "Wołający jest jeden i jest nazwany").
    require_authenticated_principal: bool = False

    @field_validator("teams_url")
    @classmethod
    def _not_blank(cls, value: str, info: ValidationInfo) -> str:
        if not value.strip():
            raise ValueError(f"{str(info.field_name).upper()} is set but empty")
        return value.rstrip("/")

    @field_validator("teams_scope")
    @classmethod
    def _blank_scope_means_unset(cls, value: str | None) -> str | None:
        # TEAMS_SCOPE= left in a .env is the same intent as the line being absent —
        # local mode — not a scope named "".
        if value is None or not value.strip():
            return None
        return value.strip()

    @field_validator("teams_request_timeout_seconds")
    @classmethod
    def _timeout_is_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError(f"TEAMS_REQUEST_TIMEOUT_SECONDS must be positive, got {value}")
        return value

    @property
    def operator_identity_optional(self) -> bool:
        """Whether a call may proceed with no operator identity behind it — true only on a
        machine where no layer could have issued one (specs/teams-mcp-authorship, "Brak
        tożsamości operatora zatrzymuje zapis, nie podstawia zastępczej").

        **Both conditions, and they are about different hops.** The flag is about what
        stands in front of *this* module; the address is about the `teams` that would
        validate the forwarded token and attribute the rows. Either one alone is a
        plausible misconfiguration — an instance with the flag off pointed at a remote
        `teams` through a tunnel would write to the real catalogue as whatever that
        instance's `teams` calls an unauthenticated caller — so the carve-out asks for the
        whole local shape (design.md, "Dwa warunki, nie jeden").

        Azure is on the refusing side of both: `REQUIRE_AUTHENTICATED_PRINCIPAL = "true"`
        and a remote `TEAMS_URL` (`infra/app-service.tf`).
        """
        return not self.require_authenticated_principal and points_at_loopback(self.teams_url)

    @model_validator(mode="after")
    def _upstream_mode_is_coherent(self) -> Settings:
        is_loopback = points_at_loopback(self.teams_url)

        if self.teams_scope is not None:
            if is_loopback:
                raise ValueError(
                    f"TEAMS_SCOPE is set but TEAMS_URL points at loopback "
                    f"({self.teams_url!r}) — a scope belongs to a remote teams; unset "
                    "TEAMS_SCOPE for local development, or point the URL at the remote "
                    "instance it names a token for."
                )
            return self

        if not is_loopback:
            raise ValueError(
                f"TEAMS_URL points at {(urlparse(self.teams_url).hostname or '').lower()!r} "
                "with no TEAMS_SCOPE set. Without a scope "
                "this module only connects to a teams on this machine's loopback — a "
                "remote one needs TEAMS_SCOPE and the managed identity it is requested for."
            )
        return self
