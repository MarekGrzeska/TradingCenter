"""What each model call inside a run cost — one row per call, priced at write time.

A twin of agent's own `usage` table, scoped to a run step instead of a message: every
wywołanie modelu inside a run leaves its own row, never aggregated at write time
(specs/teams-usage, "Każde wywołanie modelu zostawia własny wiersz zużycia") — a run
with N agents called M times each leaves N×M rows, which is what lets `GET /usage`
answer "how much did each agent cost" as a `GROUP BY run_step_id` rather than a number
nothing can be subtracted from.

`input_rate_per_1m` / `output_rate_per_1m` are snapshotted from the model catalogue at
write time, the same as agent's, and for the same reason: a cennik changed after a run
MUST NOT reprice it retroactively (specs/teams-usage, "Koszt jest przypisany do wiersza
w chwili zapisu").

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


def upgrade() -> None:
    op.create_table(
        "usage",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "run_id",
            sa.BigInteger(),
            sa.ForeignKey("runs.id", name="usage_run_id_fkey", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "run_step_id",
            sa.BigInteger(),
            sa.ForeignKey("run_steps.id", name="usage_run_step_id_fkey", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("model_id", sa.Text(), nullable=False),
        # NULL, not zero, when the provider reported nothing for this call — a wiersz
        # MUST distinguish "zero tokens" from "unknown" (specs/teams-usage).
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cached_tokens", sa.Integer(), nullable=True),
        sa.Column("reasoning_tokens", sa.Integer(), nullable=True),
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
    op.create_index("ix_usage_run_id", "usage", ["run_id"])
    # The "koszt per agent" read `GET /usage` exists for (specs/teams-usage, "Odczyt
    # zużycia w rozbiciu na role").
    op.create_index("ix_usage_run_step_id", "usage", ["run_step_id"])
    op.create_index("ix_usage_model_created", "usage", ["model_id", "created_at"])


def downgrade() -> None:
    op.drop_table("usage")
