"""The candle table — the archive's reason to exist.

Revision ID: 0001
Revises:
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Spelled out rather than imported from `market_data.models`. A migration is a record of
# what was run against a database on a given day; importing today's enum would let a
# later edit rewrite history and make an old migration mean something new.
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
        "candles",
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("resolution", sa.Text(), nullable=False),
        # The start of the period, not its end and not the moment it arrived. `timestamptz`
        # so the stored value is an instant; a `timestamp` would keep whatever wall clock
        # the writer happened to have.
        sa.Column("period_start", sa.TIMESTAMP(timezone=True), nullable=False),
        # Written, never inferred. Everything here is the bid side today, the side the
        # gateway builds both history and stream from. Recording it means that the day a
        # second side arrives, the mixture is a migration someone has to perform rather
        # than a silent averaging of two series.
        sa.Column("price_side", sa.Text(), nullable=False, server_default="bid"),
        # Edges are nullable because the provider's are: it occasionally omits one, and a
        # candle missing an edge is still better evidence than a gap.
        sa.Column("open", sa.Double(), nullable=True),
        sa.Column("high", sa.Double(), nullable=True),
        sa.Column("low", sa.Double(), nullable=True),
        sa.Column("close", sa.Double(), nullable=True),
        sa.Column("volume", sa.Double(), nullable=True),
        # Which way it arrived. A history read sees a period whole; a stream that was
        # disconnected understates it. Deciding which value survives a collision is
        # impossible without knowing this.
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column(
            "recorded_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # Identity is the triple, so a second write of the same period is an overwrite
        # rather than a second row. This index is also the one a range read uses: its
        # leading columns are the equality filter and its last is the ordering, so
        # "candles for this pair between two moments, oldest first" needs nothing else.
        sa.PrimaryKeyConstraint("symbol", "resolution", "period_start", name="candles_pkey"),
        sa.CheckConstraint(_in_list("resolution", RESOLUTIONS), name="candles_resolution_known"),
        sa.CheckConstraint(_in_list("price_side", ("bid", "ask")), name="candles_price_side_known"),
        sa.CheckConstraint(_in_list("source", ("history", "stream")), name="candles_source_known"),
    )


def downgrade() -> None:
    op.drop_table("candles")
