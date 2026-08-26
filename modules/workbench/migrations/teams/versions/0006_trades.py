"""Every call a run made that could change the account, in a table of its own rather than a read over `tool_calls`: the
daily limit counts orders before a run exists, and counting inside another module's JSON breaks when it renames a field.

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

# sent — written and the call went out; settled — the server answered with a settled result; unsettled — answered with
# a reference; refused — answered no; unknown — the call failed in a way that says nothing about whether it arrived.
_STATUSES = ("sent", "settled", "unsettled", "refused", "unknown")


def upgrade() -> None:
    op.create_table(
        "trades",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "run_id",
            sa.BigInteger(),
            sa.ForeignKey("runs.id", name="trades_run_id_fkey", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "run_step_id",
            sa.BigInteger(),
            sa.ForeignKey("run_steps.id", name="trades_run_step_id_fkey", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("agent_key", sa.Text(), nullable=False),
        sa.Column("tool_name", sa.Text(), nullable=False),
        # Read off the call's own arguments where they are there to read. NULL is "this kind of order does
        # not have one", never "we lost it" — the arguments themselves stay in `tool_calls` either way.
        sa.Column("symbol", sa.Text(), nullable=True),
        sa.Column("direction", sa.Text(), nullable=True),
        sa.Column("size", sa.Numeric(18, 8), nullable=True),
        sa.Column("level", sa.Numeric(18, 8), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="sent"),
        # What the provider called it. Kept beside `status` rather than folded into it: that column is
        # this module's own reading of the outcome, this one is the upstream's word for it.
        sa.Column("result_status", sa.Text(), nullable=True),
        sa.Column("provider_order_id", sa.Text(), nullable=True),
        sa.Column("reference", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("settled_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN (" + ", ".join(f"'{status}'" for status in _STATUSES) + ")",
            name="trades_status_known",
        ),
        sa.CheckConstraint("size IS NULL OR size > 0", name="trades_size_positive"),
    )
    op.create_index("ix_trades_run_id", "trades", ["run_id"])
    op.create_index("ix_trades_run_step_id", "trades", ["run_step_id"])
    # The daily ceiling's own read: this team's orders since midnight. `runs` carries the
    # team, so the join lands on `run_id` and the time filter on `created_at`.
    op.create_index("ix_trades_created_at", "trades", ["created_at"])


def downgrade() -> None:
    op.drop_table("trades")
