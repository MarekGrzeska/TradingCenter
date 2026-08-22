"""Backtest runs — a report kept whole, so a claim can be checked later.

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "backtest_runs",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("strategy_id", sa.Text, nullable=False),
        sa.Column("symbol", sa.Text, nullable=False),
        sa.Column("resolution", sa.Text, nullable=False),
        sa.Column("range_from", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("range_to", sa.TIMESTAMP(timezone=True), nullable=False),
        # The three things a report has to name about itself, as columns rather than only
        # inside the blob, because they are what two runs must share before their numbers
        # may be read together (`strategy-backtest`).
        sa.Column("params", postgresql.JSONB(), nullable=False),
        sa.Column("costs", postgresql.JSONB(), nullable=False),
        # The whole report as it was produced. Kept entire rather than shredded into
        # columns: a metric added next month must not make last month's runs unreadable,
        # and what makes a run worth keeping is that it can still be read as it was.
        sa.Column("report", postgresql.JSONB(), nullable=False),
        sa.Column("ran_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint("range_from < range_to", name="backtest_runs_range"),
    )
    op.create_index(
        "backtest_runs_by_strategy", "backtest_runs", ["strategy_id", sa.text("ran_at DESC")]
    )


def downgrade() -> None:
    op.drop_index("backtest_runs_by_strategy", table_name="backtest_runs")
    op.drop_table("backtest_runs")
