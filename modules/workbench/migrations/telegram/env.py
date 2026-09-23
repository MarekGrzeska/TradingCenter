"""The door to Telegram's chain. The whole of how alembic reaches a database is one copy in
`workbench/alembic_env.py`; this file says which of the seven databases this chain is."""

from __future__ import annotations

from workbench.alembic_env import run, telegram_settings

run(telegram_settings)
