"""Tracked pairs — the operator's standing decision about what gets collected.

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RESOLUTIONS = (
    "MINUTE",
    "MINUTE_5",
    "MINUTE_15",
    "MINUTE_30",
    "HOUR",
    "HOUR_4",
    "DAY",
    "WEEK",
)

STATES = ("tracked", "untracked")


def _in_list(column: str, values: Sequence[str]) -> str:
    return f"{column} IN (" + ", ".join(f"'{value}'" for value in values) + ")"


def upgrade() -> None:
    op.create_table(
        "tracked_pairs",
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("resolution", sa.Text(), nullable=False),
        # Untracking flips this rather than deleting the row: the candles stay readable, and tracking
        # again needs to know when collection stopped in order to close the gap.
        sa.Column("state", sa.Text(), nullable=False, server_default="tracked"),
        sa.Column(
            "added_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("untracked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        # This table *is* the durable configuration — there is no list in a file to drift
        # from it, and a restart reads exactly the rows marked `tracked`.
        sa.PrimaryKeyConstraint("symbol", "resolution", name="tracked_pairs_pkey"),
        sa.CheckConstraint(
            _in_list("resolution", RESOLUTIONS), name="tracked_pairs_resolution_known"
        ),
        sa.CheckConstraint(_in_list("state", STATES), name="tracked_pairs_state_known"),
        # A tracked pair cannot also carry the moment it stopped, and one that stopped must say when.
        # Without this the gap a re-added pair has to close is guesswork, and the guess is silent.
        sa.CheckConstraint(
            "(state = 'tracked' AND untracked_at IS NULL)"
            " OR (state = 'untracked' AND untracked_at IS NOT NULL)",
            name="tracked_pairs_untracked_at_matches_state",
        ),
    )


def downgrade() -> None:
    op.drop_table("tracked_pairs")
