"""Where an outcome's samples turn hourly. One boundary per outcome rather than a mark on every sample kept:
the mark would be hundreds of thousands of updates on the table this change exists to shrink, and it would
say the same thing.

Revision ID: 0008
Revises: 0007
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE outcomes ADD COLUMN thinned_through timestamptz")


def downgrade() -> None:
    op.execute("ALTER TABLE outcomes DROP COLUMN thinned_through")
