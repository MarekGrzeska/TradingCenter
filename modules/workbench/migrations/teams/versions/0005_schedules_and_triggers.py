"""A team's clock: cron schedules, market-condition triggers, and the fire history that survives both — including the
fires that started nothing, because quiet for want of work looks identical to quiet against a ceiling.

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REVISION_MODES = ("pinned", "latest")
FIRE_OUTCOMES = ("started", "skipped", "unavailable")
TRIGGER_COMPARISONS = ("gt", "gte", "lt", "lte", "eq")


def _in_list(column: str, values: Sequence[str]) -> str:
    return f"{column} IN (" + ", ".join(f"'{value}'" for value in values) + ")"


# Shared by `schedules` and `triggers` — "which revision do I run" is one question asked the same way by
# both. `table` names the constraint, since both callers add these to a table SQLAlchemy has not created.
def _revision_selection_columns(table: str) -> list[sa.Column]:
    return [
        sa.Column("revision_mode", sa.Text(), nullable=False, server_default="pinned"),
        sa.Column(
            "pinned_revision_id",
            sa.BigInteger(),
            sa.ForeignKey("team_revisions.id", name=f"{table}_pinned_revision_id_fkey"),
            nullable=True,
        ),
    ]


def _unattended_safety_columns() -> list[sa.Column]:
    return [
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        # Set by the module's own auto-disable, or left NULL when an operator disabled it by hand and
        # needs no explanation of their own choice.
        sa.Column("disabled_reason", sa.Text(), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        # Refused at save time unless true, the day a revision's agent carries a state-changing tool.
        # Vacuous today — no such tool exists yet — and load-bearing the day phase 2 adds the first one.
        sa.Column("unattended_ack", sa.Boolean(), nullable=False, server_default=sa.false()),
    ]


def upgrade() -> None:
    op.create_table(
        "schedules",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "team_id",
            sa.BigInteger(),
            sa.ForeignKey("teams.id", name="schedules_team_id_fkey"),
            nullable=False,
        ),
        # Copied at creation, not read from the request that fires it — a schedule works when no browser
        # is open. The module calls nothing with this identity; it is a label the queries filter on.
        sa.Column("owner_principal", sa.Text(), nullable=False),
        *_revision_selection_columns("schedules"),
        sa.Column("cron_expression", sa.Text(), nullable=False),
        # Claimed with `UPDATE … WHERE next_fire_at <= now() RETURNING`: two processes racing this
        # statement give exactly one winner, which is what makes a fire during a deployment single.
        sa.Column("next_fire_at", sa.TIMESTAMP(timezone=True), nullable=False),
        *_unattended_safety_columns(),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(_in_list("revision_mode", REVISION_MODES), name="schedules_revision_mode_known"),
        sa.CheckConstraint(
            "(revision_mode = 'pinned' AND pinned_revision_id IS NOT NULL) OR "
            "(revision_mode = 'latest' AND pinned_revision_id IS NULL)",
            name="schedules_revision_selection_coherent",
        ),
        sa.CheckConstraint("consecutive_failures >= 0", name="schedules_failures_nonneg"),
    )
    # The claim statement's own WHERE clause — every wake of the clock scans exactly
    # the enabled schedules that are due, not the whole table.
    op.create_index(
        "ix_schedules_next_fire",
        "schedules",
        ["next_fire_at"],
        postgresql_where=sa.text("enabled"),
    )
    op.create_index("ix_schedules_owner", "schedules", ["owner_principal"])
    op.create_index("ix_schedules_team", "schedules", ["team_id"])

    op.create_table(
        "triggers",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "team_id",
            sa.BigInteger(),
            sa.ForeignKey("teams.id", name="triggers_team_id_fkey"),
            nullable=False,
        ),
        sa.Column("owner_principal", sa.Text(), nullable=False),
        *_revision_selection_columns("triggers"),
        # The condition, expressed as a call to a tool this module already has a session for — never a
        # locally computed indicator. `field_path` reads one value out of that call's JSON result.
        sa.Column("tool_name", sa.Text(), nullable=False),
        sa.Column("arguments", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("field_path", sa.Text(), nullable=False),
        sa.Column("comparison", sa.Text(), nullable=False),
        sa.Column("threshold", sa.Numeric(18, 8), nullable=False),
        # How long after a fire the condition is not asked again, even if it is still
        # true (specs/teams-triggers, "Wyzwalacz reaguje na zbocze, nie na stan").
        sa.Column("cooldown_seconds", sa.Integer(), nullable=False, server_default="900"),
        # How often the condition is checked at all — a second, coarser cadence than
        # `cooldown_seconds`, which only bounds re-fires once one has happened.
        sa.Column("poll_interval_seconds", sa.Integer(), nullable=False, server_default="300"),
        sa.Column(
            "next_check_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # NULL is a third value, not "false": the tool server being unreachable is not the same fact as
        # the condition being unmet, and this column is what the edge detection compares against.
        sa.Column("last_result", sa.Boolean(), nullable=True),
        sa.Column("last_checked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_fired_at", sa.TIMESTAMP(timezone=True), nullable=True),
        *_unattended_safety_columns(),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(_in_list("revision_mode", REVISION_MODES), name="triggers_revision_mode_known"),
        sa.CheckConstraint(
            "(revision_mode = 'pinned' AND pinned_revision_id IS NOT NULL) OR "
            "(revision_mode = 'latest' AND pinned_revision_id IS NULL)",
            name="triggers_revision_selection_coherent",
        ),
        sa.CheckConstraint(_in_list("comparison", TRIGGER_COMPARISONS), name="triggers_comparison_known"),
        sa.CheckConstraint("cooldown_seconds > 0", name="triggers_cooldown_positive"),
        sa.CheckConstraint("poll_interval_seconds > 0", name="triggers_poll_interval_positive"),
        sa.CheckConstraint("consecutive_failures >= 0", name="triggers_failures_nonneg"),
    )
    op.create_index(
        "ix_triggers_next_check",
        "triggers",
        ["next_check_at"],
        postgresql_where=sa.text("enabled"),
    )
    op.create_index("ix_triggers_owner", "triggers", ["owner_principal"])
    op.create_index("ix_triggers_team", "triggers", ["team_id"])

    op.create_table(
        "schedule_fires",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "schedule_id",
            sa.BigInteger(),
            sa.ForeignKey("schedules.id", name="schedule_fires_schedule_id_fkey"),
            nullable=True,
        ),
        sa.Column(
            "trigger_id",
            sa.BigInteger(),
            sa.ForeignKey("triggers.id", name="schedule_fires_trigger_id_fkey"),
            nullable=True,
        ),
        sa.Column(
            "fired_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("outcome", sa.Text(), nullable=False),
        # Names the reason a fire started nothing: a previous run still working, the team's daily ceiling,
        # a revision that no longer runs, or the tool server being unreachable.
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "run_id",
            sa.BigInteger(),
            sa.ForeignKey("runs.id", name="schedule_fires_run_id_fkey"),
            nullable=True,
        ),
        # How many due fires were collapsed into this one after the module was not running to see them —
        # 0 for the ordinary case of a schedule that was never behind.
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint(
            "(schedule_id IS NOT NULL AND trigger_id IS NULL) OR "
            "(schedule_id IS NULL AND trigger_id IS NOT NULL)",
            name="schedule_fires_exactly_one_source",
        ),
        sa.CheckConstraint(_in_list("outcome", FIRE_OUTCOMES), name="schedule_fires_outcome_known"),
        sa.CheckConstraint(
            "(outcome = 'started' AND run_id IS NOT NULL AND reason IS NULL) OR "
            "(outcome IN ('skipped', 'unavailable') AND run_id IS NULL AND reason IS NOT NULL)",
            name="schedule_fires_outcome_coherent",
        ),
        sa.CheckConstraint("skipped_count >= 0", name="schedule_fires_skipped_count_nonneg"),
    )
    op.create_index(
        "ix_schedule_fires_schedule",
        "schedule_fires",
        ["schedule_id", sa.text("fired_at DESC")],
    )
    op.create_index(
        "ix_schedule_fires_trigger",
        "schedule_fires",
        ["trigger_id", sa.text("fired_at DESC")],
    )


def downgrade() -> None:
    op.drop_table("schedule_fires")
    op.drop_table("triggers")
    op.drop_table("schedules")
