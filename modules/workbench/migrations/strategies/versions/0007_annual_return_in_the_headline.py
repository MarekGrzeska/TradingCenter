"""The annual return in each run's headline, so a list compares runs of different lengths without opening their reports.

Revision ID: 0007
Revises: 0006
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Copied from the report each run already has rather than recomputed: a recorded result is never recomputed.
    op.execute(
        """
        UPDATE runs SET headline = headline || jsonb_build_object('annual_return_pct', report->'annual_return_pct')
        WHERE headline IS NOT NULL AND report IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("UPDATE runs SET headline = headline - 'annual_return_pct' WHERE headline IS NOT NULL")
