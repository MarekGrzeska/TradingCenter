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

from urllib.parse import urlparse

from pydantic import ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Any host carrying this belongs to the provider. Matched as a substring on purpose:
# the demo, live and streaming hosts are all variants of it, and a rule tight enough
# to name one of them is loose enough to let the others through.
PROVIDER_HOST_MARKER = "capital.com"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- the gateway, this module's only upstream ---
    gateway_base_url: str = "http://localhost:8010"
    gateway_stream_url: str = "ws://localhost:8010/ws/stream"

    # --- the archive's own storage ---
    database_url: str

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

    @field_validator("database_url")
    @classmethod
    def _database_present(cls, value: str) -> str:
        # pydantic already rejects a variable that is absent; this catches the one that is
        # present but empty, which is what an unfilled .env actually looks like.
        if not value.strip():
            raise ValueError("DATABASE_URL is set but empty")
        return value.strip()

    @field_validator("backfill_concurrency", "default_backfill_bars", "max_tracked_pairs")
    @classmethod
    def _positive(cls, value: int, info: ValidationInfo) -> int:
        if value < 1:
            raise ValueError(f"{str(info.field_name).upper()} must be at least 1; got {value}")
        return value
