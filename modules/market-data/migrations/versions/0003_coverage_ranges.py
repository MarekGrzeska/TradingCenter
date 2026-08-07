"""Coverage ranges — what the archive has actually verified, as opposed to merely lacks.

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
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
        "coverage_ranges",
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("resolution", sa.Text(), nullable=False),
        sa.Column("range_start", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("range_end", sa.TIMESTAMP(timezone=True), nullable=False),
        # Set when the provider answered that it has nothing older than `range_start`.
        # The gateway already publishes this as `history_ended` on a deep read; dropping it
        # would mean asking forever for data that does not exist.
        sa.Column("history_ended", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "verified_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # Keyed by where the range begins, which is what a lookup filters on: "is this
        # moment inside anything verified for this pair" walks the same leading columns.
        sa.PrimaryKeyConstraint(
            "symbol", "resolution", "range_start", name="coverage_ranges_pkey"
        ),
        sa.CheckConstraint(
            _in_list("resolution", RESOLUTIONS), name="coverage_ranges_resolution_known"
        ),
        # An empty range is allowed — a single verified period has start == end — but an
        # inverted one is a bug that would silently cover nothing.
        sa.CheckConstraint("range_end >= range_start", name="coverage_ranges_not_inverted"),
    )
    # A pair has at most one oldest-possible boundary. Two of them would mean two different
    # answers to "how far back is there anything to fetch", and backfill would believe
    # whichever it read first.
    op.create_index(
        "coverage_ranges_one_history_end_per_pair",
        "coverage_ranges",
        ["symbol", "resolution"],
        unique=True,
        postgresql_where=sa.text("history_ended"),
    )


def downgrade() -> None:
    op.drop_index("coverage_ranges_one_history_end_per_pair", table_name="coverage_ranges")
    op.drop_table("coverage_ranges")
