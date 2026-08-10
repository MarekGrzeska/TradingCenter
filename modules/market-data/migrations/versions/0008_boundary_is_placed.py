"""A boundary and the point it lies at are one fact, enforced.

Split from 0007 for a deployment reason rather than a schema one. 0007 adds the column
and must be applied *before* the code that fills it — new code against the old schema
answers 500 to every coverage read. This constraint must be applied *after* it: the old
writer inserts five columns, so a row it writes on finding the end of history would carry
the flag and no point, and be refused.

Between the two, a row written by the old code can hold the flag without a point. It
reads as "boundary unknown" rather than as a boundary in the wrong place, and the next
measurement replaces it — which is why the gap is safe to leave open for one deploy. Any
such row is cleared here rather than blocking the constraint, for the same reason: the
claim is unusable without a point, and re-measuring it costs one request.

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
    op.execute(
        "UPDATE coverage_ranges SET history_ended = false "
        " WHERE history_ended AND history_ends_at IS NULL"
    )
    op.create_check_constraint(
        "coverage_ranges_boundary_is_placed",
        "coverage_ranges",
        "(history_ended) = (history_ends_at IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("coverage_ranges_boundary_is_placed", "coverage_ranges")
