"""The conversion of the old settings has run, and the table that said so is no longer needed.

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS migrations_done")


def downgrade() -> None:
    op.execute(
        """
        CREATE TABLE migrations_done (
            name     text PRIMARY KEY,
            done_at  timestamptz NOT NULL DEFAULT now()
        )
        """
    )
