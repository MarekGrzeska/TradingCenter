"""Sessions, their transcript, and the usage each model call leaves behind.

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

ROLES = ("operator", "agent")


def _in_list(column: str, values: Sequence[str]) -> str:
    return f"{column} IN (" + ", ".join(f"'{value}'" for value in values) + ")"


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        # Who this rozmowa belongs to — the Easy Auth principal, or the constant "local" identity a
        # module started without the requirement assigns. Every read is filtered by this.
        sa.Column("owner_principal", sa.Text(), nullable=False),
        # NULL until the first exchange — the same flag that keeps an empty session off the list: a
        # listing query is `WHERE title IS NOT NULL`, nothing more.
        sa.Column("title", sa.Text(), nullable=True),
        # The model the *next* turn will use. Each agent message carries the model that produced it,
        # because changing this MUST NOT rewrite what earlier turns were answered with.
        sa.Column("current_model_id", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # Ordered by for the session list — an operator returns to the rozmowa they just
        # left far more often than to one from last week.
        sa.Column(
            "last_active_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # Set when the operator removes a rozmowa. A stamp rather than a `DELETE`, because `usage` rows
        # reference this session and money spent must not stop being counted. Every read filters on it.
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_sessions_owner_last_active",
        "sessions",
        ["owner_principal", sa.text("last_active_at DESC")],
    )

    op.create_table(
        "messages",
        # A plain Identity PK, not a per-session sequence: it is already globally monotonic, so ordering
        # a transcript by `(session_id, id)` is repeatable without a second counter.
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "session_id",
            sa.BigInteger(),
            sa.ForeignKey("sessions.id", name="messages_session_id_fkey"),
            nullable=False,
        ),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        # Set on an agent message only — which model and which system prompt produced it, kept even
        # after the model is retired from the catalogue.
        sa.Column("model_id", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.Text(), nullable=True),
        # A stream that broke before the model finished still leaves this row, with whatever text
        # arrived, marked so a reader can tell a cut answer from a complete one.
        sa.Column("incomplete", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(_in_list("role", ROLES), name="messages_role_known"),
        sa.CheckConstraint(
            "(role = 'operator' AND model_id IS NULL AND prompt_version IS NULL "
            "AND incomplete = false) OR "
            "(role = 'agent' AND model_id IS NOT NULL AND prompt_version IS NOT NULL)",
            name="messages_model_fields_match_role",
        ),
    )
    op.create_index("ix_messages_session_id", "messages", ["session_id", "id"])

    op.create_table(
        "usage",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "session_id",
            sa.BigInteger(),
            sa.ForeignKey("sessions.id", name="usage_session_id_fkey"),
            nullable=False,
        ),
        sa.Column(
            "message_id",
            sa.BigInteger(),
            sa.ForeignKey("messages.id", name="usage_message_id_fkey"),
            nullable=False,
        ),
        sa.Column("model_id", sa.Text(), nullable=False),
        # NULL, not zero, when the provider reported nothing for this call — a wiersz
        # MUST distinguish "zero tokens" from "unknown" (specs/agent-usage).
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cached_tokens", sa.Integer(), nullable=True),
        sa.Column("reasoning_tokens", sa.Integer(), nullable=True),
        # The rate this row was priced at, snapshotted at write time and never re-read from current
        # configuration. Per 1,000,000 tokens; 8 decimal places keeps the cost column exact.
        sa.Column("input_rate_per_1m", sa.Numeric(18, 8), nullable=False),
        sa.Column("output_rate_per_1m", sa.Numeric(18, 8), nullable=False),
        # NULL exactly when the tokens it would be computed from are — a cost cannot be
        # invented for usage the provider never reported.
        sa.Column("cost", sa.Numeric(18, 8), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("input_tokens IS NULL OR input_tokens >= 0", name="usage_input_tokens_nonneg"),
        sa.CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0", name="usage_output_tokens_nonneg"
        ),
        sa.CheckConstraint(
            "cached_tokens IS NULL OR cached_tokens >= 0", name="usage_cached_tokens_nonneg"
        ),
        sa.CheckConstraint(
            "reasoning_tokens IS NULL OR reasoning_tokens >= 0", name="usage_reasoning_tokens_nonneg"
        ),
        sa.CheckConstraint("input_rate_per_1m > 0", name="usage_input_rate_positive"),
        sa.CheckConstraint("output_rate_per_1m > 0", name="usage_output_rate_positive"),
        sa.CheckConstraint("cost IS NULL OR cost >= 0", name="usage_cost_nonneg"),
        # Cost is derived from tokens; a row cannot carry one without the other, or a
        # later reader cannot tell whether a cost came from real usage or was guessed.
        sa.CheckConstraint(
            "cost IS NULL OR (input_tokens IS NOT NULL AND output_tokens IS NOT NULL)",
            name="usage_cost_needs_tokens",
        ),
    )
    op.create_index("ix_usage_session_id", "usage", ["session_id"])
    op.create_index("ix_usage_model_created", "usage", ["model_id", "created_at"])


def downgrade() -> None:
    op.drop_table("usage")
    op.drop_table("messages")
    op.drop_table("sessions")
