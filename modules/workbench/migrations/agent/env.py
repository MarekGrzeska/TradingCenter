"""The conversation's chain. The whole of how alembic reaches a database is one copy in
`workbench/alembic_env.py`; this file says which of the two databases this chain is."""

from __future__ import annotations

from workbench.alembic_env import conversation_settings, run

run(conversation_settings)
