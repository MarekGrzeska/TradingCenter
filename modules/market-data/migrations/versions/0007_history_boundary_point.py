"""Where the provider's history actually ends, as its own column.

`history_ended` said only *that* a boundary exists; where it lay was read off
`range_start`. Those are the same point only for a range nothing ever merged with, and
coverage ranges merge by design — a fill meeting an older one end to end becomes a single
row whose start is the older edge. So the boundary drifted to the earliest moment the
pair had ever verified, which is not where the provider ran out and is usually a long way
below it.

Backfilled to `range_start` for the rows that already claim a boundary, because that is
what those rows meant when they were written. It is the wrong point for any of them that
merged since — the reason for this column — and no better value exists in the data. A
deeper request now drops the boundary and re-measures it, which is the recovery path.

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
