"""The strategy platform's chain. The whole of how alembic reaches a database is one copy in
`workbench/alembic_env.py`; this file says which of the five databases this chain is."""

from __future__ import annotations

from workbench.alembic_env import run, strategy_settings

run(strategy_settings)
