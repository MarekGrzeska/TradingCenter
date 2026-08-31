"""What the agent asked market-mcp for, and what came back. Deliberately not a row in `messages`: that
table is the transcript, and a tool call is how the agent got to its answer.

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

# The three answers a call can end in, and they are not interchangeable: `refused` means the server
# answered and named what to change, `unavailable` that it never answered at all.
OUTCOMES = ("ok", "refused", "unavailable")


def _in_list(column: str, values: Sequence[str]) -> str:
    return f"{column} IN (" + ", ".join(f"'{value}'" for value in values) + ")"


def upgrade() -> None:
    op.create_table(
        "tool_calls",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "session_id",
            sa.BigInteger(),
            sa.ForeignKey("sessions.id", name="tool_calls_session_id_fkey"),
            nullable=False,
        ),
        # The agent's reply this call was made in service of, written after that reply exists — for the
        # same reason usage rows are: the id does not exist until the turn ends.
        sa.Column(
            "message_id",
            sa.BigInteger(),
            sa.ForeignKey("messages.id", name="tool_calls_message_id_fkey"),
            nullable=False,
        ),
        # Which round of the turn asked for it, and the position within that round. Together with `id`
        # they make the order recoverable without trusting a timestamp.
        sa.Column("round_index", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("tool_name", sa.Text(), nullable=False),
        # JSONB rather than text: the arguments are a JSON object on the wire, and a
        # reader asking "which symbol did it look up" should not have to parse a string.
        sa.Column("arguments", postgresql.JSONB(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        # The tool's answer, or the sentence it refused with, or the one naming the
        # outage — all three are prose from market-mcp and all three are worth keeping.
        sa.Column("result_text", sa.Text(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(_in_list("outcome", OUTCOMES), name="tool_calls_outcome_known"),
        sa.CheckConstraint("round_index >= 0", name="tool_calls_round_index_nonneg"),
        sa.CheckConstraint("position >= 0", name="tool_calls_position_nonneg"),
        sa.CheckConstraint("duration_ms >= 0", name="tool_calls_duration_nonneg"),
    )
    # The one read this table is for: everything one reply asked for, in order.
    op.create_index(
        "ix_tool_calls_message",
        "tool_calls",
        ["message_id", "round_index", "position"],
    )
    op.create_index("ix_tool_calls_session_id", "tool_calls", ["session_id"])


def downgrade() -> None:
    op.drop_table("tool_calls")
