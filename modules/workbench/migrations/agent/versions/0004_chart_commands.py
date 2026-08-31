"""What the agent set the terminal's chart to. A command, not a state: keeping it a log is what keeps the
terminal the owner of what it draws, and null is how a command says nothing about a field.

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chart_commands",
        # The sequence the terminal remembers. `Identity` rises across the whole table and therefore
        # across every conversation — the terminal has one chart, and one cursor for it.
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "session_id",
            sa.BigInteger(),
            sa.ForeignKey("sessions.id", name="chart_commands_session_id_fkey"),
            nullable=False,
        ),
        sa.Column("symbol", sa.Text(), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=True),
        # JSONB for the same reason `tool_calls.arguments` is: this is a JSON array on the wire. Null
        # and `[]` are different answers — see the check below.
        sa.Column("indicators", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # A command that sets nothing is not a command. Without this the log would grow
        # rows a consumer must read to discover they say nothing.
        sa.CheckConstraint(
            "symbol IS NOT NULL OR resolution IS NOT NULL OR indicators IS NOT NULL",
            name="chart_commands_sets_something",
        ),
    )
    # The one read: everything newer than the cursor, in order. The primary key's own
    # index answers it, so there is no second index here on purpose.


def downgrade() -> None:
    op.drop_table("chart_commands")
