"""A run of a team revision, its per-agent steps and their tool calls. A run always names the revision it ran on, which
is the whole reason `team_revisions` is append-only; `run_steps` is one row per agent rather than per round.

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

RUN_STATUSES = ("pending", "running", "completed", "failed", "cancelled")
STEP_STATUSES = ("pending", "running", "completed", "failed")
TOOL_OUTCOMES = ("ok", "refused", "unavailable")


def _in_list(column: str, values: Sequence[str]) -> str:
    return f"{column} IN (" + ", ".join(f"'{value}'" for value in values) + ")"


def upgrade() -> None:
    op.create_table(
        "runs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "team_revision_id",
            sa.BigInteger(),
            sa.ForeignKey("team_revisions.id", name="runs_team_revision_id_fkey"),
            nullable=False,
        ),
        # Ownership mirrors `teams.owner_principal` rather than being read through the revision chain: a
        # run's own access check MUST NOT depend on a join.
        sa.Column("owner_principal", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        # Set exactly when status lands on `failed` or `cancelled` — names the cost limit, the time
        # limit, a tool-access refusal, or the operator's own interruption.
        sa.Column("stopped_reason", sa.Text(), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(_in_list("status", RUN_STATUSES), name="runs_status_known"),
        sa.CheckConstraint(
            "(status IN ('pending', 'running') AND stopped_reason IS NULL "
            "  AND finished_at IS NULL) OR "
            "(status = 'completed' AND stopped_reason IS NULL AND finished_at IS NOT NULL) OR "
            "(status IN ('failed', 'cancelled') AND stopped_reason IS NOT NULL "
            "  AND finished_at IS NOT NULL)",
            name="runs_status_fields_match",
        ),
    )
    op.create_index("ix_runs_team_revision_id", "runs", ["team_revision_id"])
    op.create_index(
        "ix_runs_owner_created",
        "runs",
        ["owner_principal", sa.text("created_at DESC")],
    )

    op.create_table(
        "run_steps",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "run_id",
            sa.BigInteger(),
            sa.ForeignKey("runs.id", name="run_steps_run_id_fkey", ondelete="CASCADE"),
            nullable=False,
        ),
        # The node key from the revision's `definition`, not a display name — stable
        # even if the operator's next revision renames the role.
        sa.Column("agent_key", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        # What this agent handed to its dependents — NULL until it finishes.
        sa.Column("output", sa.Text(), nullable=True),
        sa.Column("rounds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("run_id", "agent_key", name="run_steps_run_agent_unique"),
        sa.CheckConstraint(_in_list("status", STEP_STATUSES), name="run_steps_status_known"),
        sa.CheckConstraint("rounds >= 0", name="run_steps_rounds_nonneg"),
        sa.CheckConstraint(
            "(status IN ('pending', 'running') AND finished_at IS NULL) OR "
            "(status = 'completed' AND finished_at IS NOT NULL AND output IS NOT NULL) OR "
            "(status = 'failed' AND finished_at IS NOT NULL)",
            name="run_steps_status_fields_match",
        ),
    )

    op.create_table(
        "tool_calls",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        # Denormalized alongside `run_step_id`, the same shape agent's own `tool_calls` has: the one read
        # this table exists for is "everything a run called", which should need no join to answer.
        sa.Column(
            "run_id",
            sa.BigInteger(),
            sa.ForeignKey("runs.id", name="tool_calls_run_id_fkey", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "run_step_id",
            sa.BigInteger(),
            sa.ForeignKey("run_steps.id", name="tool_calls_run_step_id_fkey", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("round_index", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("tool_name", sa.Text(), nullable=False),
        sa.Column("arguments", postgresql.JSONB(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("result_text", sa.Text(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(_in_list("outcome", TOOL_OUTCOMES), name="tool_calls_outcome_known"),
        sa.CheckConstraint("round_index >= 0", name="tool_calls_round_index_nonneg"),
        sa.CheckConstraint("position >= 0", name="tool_calls_position_nonneg"),
        sa.CheckConstraint("duration_ms >= 0", name="tool_calls_duration_nonneg"),
    )
    op.create_index(
        "ix_tool_calls_run_step",
        "tool_calls",
        ["run_step_id", "round_index", "position"],
    )
    op.create_index("ix_tool_calls_run_id", "tool_calls", ["run_id"])


def downgrade() -> None:
    op.drop_table("tool_calls")
    op.drop_table("run_steps")
    op.drop_table("runs")
