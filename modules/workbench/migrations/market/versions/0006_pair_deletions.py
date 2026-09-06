"""Pair deletions — a durable record of what skasowanie removed, and when.

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
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


def _in_list(column: str, values: Sequence[str]) -> str:
    return f"{column} IN (" + ", ".join(f"'{value}'" for value in values) + ")"


def upgrade() -> None:
    op.create_table(
        "pair_deletions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("resolution", sa.Text(), nullable=False),
        sa.Column(
            "deleted_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("candles_removed", sa.Integer(), nullable=False),
        # Both null together when nothing had ever been collected for this pair — a deletion is
        # still worth recording even though there is no range to name.
        sa.Column("removed_from", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("removed_to", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint(
            "candles_removed >= 0", name="pair_deletions_candles_removed_not_negative"
        ),
        sa.CheckConstraint(
            _in_list("resolution", RESOLUTIONS), name="pair_deletions_resolution_known"
        ),
        sa.CheckConstraint(
            "(removed_from IS NULL) = (removed_to IS NULL)",
            name="pair_deletions_range_matches",
        ),
        # A deletion names a pair tracking has actually decided on at some point, the
        # same guarantee `collection_job_chunks` makes for a chunk (0005).
        sa.ForeignKeyConstraint(
            ["symbol", "resolution"],
            ["tracked_pairs.symbol", "tracked_pairs.resolution"],
            name="pair_deletions_pair_fkey",
        ),
    )
    # What `GET /deletions` scans when narrowed to a pair, and what the terminal's
    # combined history reads for one instrument.
    op.create_index("pair_deletions_pair_idx", "pair_deletions", ["symbol", "resolution"])


def downgrade() -> None:
    op.drop_index("pair_deletions_pair_idx", table_name="pair_deletions")
    op.drop_table("pair_deletions")
