"""The teams suite's name for the shared stand-in, plus the one thing that is its own. The harness is
`tests/mcp_stand_in.py` now; what stays here is `settings_for`, because each surface builds its own class."""

from __future__ import annotations

from teams.config import Settings

from ..mcp_stand_in import (
    DEFAULT_TOOLS,
    READ_ONLY,
    free_port,
    serving,
    serving_app,
    serving_sync,
)

__all__ = [
    "DEFAULT_TOOLS",
    "READ_ONLY",
    "free_port",
    "serving",
    "serving_app",
    "serving_sync",
    "settings_for",
]

ONE_MODEL = [
    {
        "id": "gpt-5.6-luna",
        "model": "luna-prod",
        "display_name": "Luna",
        "cost_rank": 1,
        "input_rate_per_1m": "1",
        "output_rate_per_1m": "6",
    }
]


def settings_for(url: str | None, **overrides) -> Settings:
    return Settings(
        database_url="postgresql://localhost:5432/teams",
        openai_api_key="key",
        models=ONE_MODEL,  # type: ignore[arg-type]
        market_mcp_url=url,
        _env_file=None,  # type: ignore[call-arg]
        **overrides,
    )
