"""A trade a step sends carries the key of its attempt, unique, so one signal bar is acted on at most once.

NULL for every agent's trade and every trade before this column: the guarantee belongs to steps (`teams-steps`).

Revision ID: 0014
Revises: 0013
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE trades ADD COLUMN attempt_key text")
    op.execute("CREATE UNIQUE INDEX ux_trades_attempt_key ON trades (attempt_key) WHERE attempt_key IS NOT NULL")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_trades_attempt_key")
    op.execute("ALTER TABLE trades DROP COLUMN IF EXISTS attempt_key")
