"""Where the provider's history actually ends, as its own column. `history_ended` said only *that* a
boundary exists, and reading it off `range_start` drifted as coverage ranges merged.

Backfilled to `range_start` for rows that already claim a boundary: no better value exists, and a
deeper request now drops the boundary and re-measures it.

Revision ID: 0007
Revises: 0006
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "coverage_ranges",
        sa.Column("history_ends_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE coverage_ranges SET history_ends_at = range_start WHERE history_ended"
    )
    # The two halves of one fact: a row either names a boundary and says it has one, or
    # does neither. Split them and "how deep does this pair go" has two answers.
    op.create_check_constraint(
        "coverage_ranges_boundary_is_placed",
        "coverage_ranges",
        "(history_ended) = (history_ends_at IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("coverage_ranges_boundary_is_placed", "coverage_ranges")
    op.drop_column("coverage_ranges", "history_ends_at")
