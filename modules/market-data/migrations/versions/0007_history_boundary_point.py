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

Nothing but the column here, deliberately. The rule tying it to `history_ended` is a
check constraint and lives in 0008, because the code that satisfies it is the code this
migration precedes: the writer running while this is applied still inserts five columns,
and a constraint added here would fail its next write that found the end of history.
Ordering is the operator's — migrations do not ride with the image (`Dockerfile`, 8.6) —
so a step that only works after the deploy has to be its own step.

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


def downgrade() -> None:
    op.drop_column("coverage_ranges", "history_ends_at")
