"""Every call a run made that could change the account, and what came of it.

A table of its own rather than a read over `tool_calls`, and the reason is the daily
limit: it has to count this team's orders *before* a run is created, and the terminal has
to list a run's own. Both off `tool_calls` would mean querying inside a JSON document
whose shape belongs to another module — `trading-mcp` renaming one field would break the
counting silently (design.md, "Ślad handlowy dostaje własną tabelę").

`tool_calls` does not lose anything: a write still leaves its row there, with the
arguments and the reply verbatim. This table is the same event read as a trade rather
than as a call.

**A row exists before the call is sent.** `status` starts at `sent` and is settled
afterwards; a row still reading `sent` after its run is over is an order whose fate this
module does not know — which is the one thing a trace of irreversible actions must be
able to say (specs/teams-trading, "Wywołanie, którego skutek pozostał nieznany").

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

# sent      — the row was written and the call went out; nothing is known yet
# settled   — the server answered with a settled result (filled, working, closed, ...)
# unsettled — the server answered, and its answer is "not resolved yet", with a reference
# refused   — the server answered no, and nothing reached the account
# unknown   — the call failed in a way that says nothing about whether it arrived
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
        # Read off the call's own arguments where they are there to read: `place_order`
        # carries all four, `close_position` carries none of them. NULL is "this kind of
        # order does not have one", never "we lost it" — the arguments themselves stay in
        # `tool_calls` either way.
        sa.Column("symbol", sa.Text(), nullable=True),
        sa.Column("direction", sa.Text(), nullable=True),
        sa.Column("size", sa.Numeric(18, 8), nullable=True),
        sa.Column("level", sa.Numeric(18, 8), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="sent"),
        # What the provider called it — FILLED, WORKING, REJECTED, PENDING. Kept beside
        # `status` rather than folded into it: that column is this module's own reading of
        # the outcome, this one is the upstream's word for it.
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
