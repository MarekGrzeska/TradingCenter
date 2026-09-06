"""Derived resolutions — computed from the minute series, never fetched.

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Only the resolutions whose period is a fixed number of seconds. DAY and WEEK follow the venue's
# session, so a derived daily candle would look right and be wrong; MINUTE is the source.
DERIVED_RESOLUTIONS = (
    "MINUTE_5",
    "MINUTE_15",
    "MINUTE_30",
    "HOUR",
    "HOUR_4",
)


def _in_list(column: str, values: Sequence[str]) -> str:
    return f"{column} IN (" + ", ".join(f"'{value}'" for value in values) + ")"


def upgrade() -> None:
    op.create_table(
        "derived_candles",
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("resolution", sa.Text(), nullable=False),
        sa.Column("period_start", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("price_side", sa.Text(), nullable=False, server_default="bid"),
        sa.Column("open", sa.Double(), nullable=True),
        sa.Column("high", sa.Double(), nullable=True),
        sa.Column("low", sa.Double(), nullable=True),
        sa.Column("close", sa.Double(), nullable=True),
        sa.Column("volume", sa.Double(), nullable=True),
        # How many minute candles went into this one, and whether that is all the period can hold.
        # A partial period still produces a candle — the last bar on a chart — but it says so.
        sa.Column("minutes_present", sa.Integer(), nullable=False),
        sa.Column("complete", sa.Boolean(), nullable=False),
        sa.Column(
            "derived_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # Same identity as an observed candle, so recomputing replaces. Its own table because computed
        # and observed values should not be indistinguishable, and a pair may be tracked here directly.
        sa.PrimaryKeyConstraint(
            "symbol", "resolution", "period_start", name="derived_candles_pkey"
        ),
        sa.CheckConstraint(
            _in_list("resolution", DERIVED_RESOLUTIONS), name="derived_candles_resolution_derivable"
        ),
        sa.CheckConstraint(
            _in_list("price_side", ("bid", "ask")), name="derived_candles_price_side_known"
        ),
        sa.CheckConstraint("minutes_present > 0", name="derived_candles_built_from_something"),
    )


def downgrade() -> None:
    op.drop_table("derived_candles")
