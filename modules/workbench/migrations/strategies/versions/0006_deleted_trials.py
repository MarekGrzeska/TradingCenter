"""The trials a strategy had before its runs were deleted: the count overfitting is judged by outlives the runs.

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE strategies ADD COLUMN deleted_trials integer NOT NULL DEFAULT 0 CHECK (deleted_trials >= 0)")


def downgrade() -> None:
    op.execute("ALTER TABLE strategies DROP COLUMN deleted_trials")
