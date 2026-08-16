"""A team's clock: cron schedules, market-condition triggers, and the fire history
that survives both — including the fires that started nothing.

Purely additive — no column touches `runs`, `team_revisions` or any table from `0001`
through `0003`. That is deliberate and organizational as much as technical: phase 2
(trading tools) is being written in parallel from the same ancestor, and a migration
that only creates tables commutes with one that only creates other tables — whichever
branch merges second just renumbers its own revision and `down_revision`
(design.md, "Punkty styku z fazą 2").

`schedules` and `triggers` share the same revision-selection shape (`revision_mode`
`pinned`/`latest`, `pinned_revision_id`) and the same unattended-work safety fields
(`enabled`, `disabled_reason`, `consecutive_failures`, `unattended_ack`) rather than
factoring it into a third table: a trigger is not "a schedule with a condition instead
of a cron field" anywhere else in this module — it has its own evaluation cadence
(`poll_interval_seconds`, `next_check_at`) and its own three-valued state
(`last_result` NULL meaning "the tool server could not be asked", not "false") — so a
shared table would need nullable columns for whichever half did not apply. Two tables
that happen to rhyme cost less than one that has to explain why half its columns are
always empty.

`schedule_fires` is one row per fire attempt from either source — including the ones
that started nothing — because that is half of what specs/teams-schedules asks an
operator to see: a schedule that is quiet because nothing is due looks identical to one
that is quiet because it keeps hitting the daily ceiling, unless the difference is
written down (specs/teams-schedules, "Wyzwolenie bez przebiegu zostawia zapisany
powód"). `runs` gets no `schedule_id` column for the same reason this table exists at
all: a fire that started nothing has no run row to hang the fact from.

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


# Shared by `schedules` and `triggers` — "which revision do I run" is one question
# asked the same way by both (design.md, "Harmonogram uruchamia rewizję przypiętą, a
# tryb «najnowsza» jest jawnym wyborem"). `table` names the constraint, since both
# callers add these columns to a table SQLAlchemy has not created yet.
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
        # Set by the module's own auto-disable (specs/teams-schedules, "Harmonogram po
        # serii nieudanych przebiegów wyłącza się sam") or left NULL when an operator
        # disabled it by hand and needs no explanation of their own choice.
        sa.Column("disabled_reason", sa.Text(), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        # Refused at save time unless true, the day a revision's agent carries a
        # state-changing tool (specs/teams-schedules, "Harmonogram nad rewizją z
        # narzędziami zapisującymi wymaga jawnego potwierdzenia"). Vacuous today — no
        # such tool exists yet — and load-bearing the day phase 2 adds the first one.
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
        # Copied at creation, not read from the request that fires it — a schedule
        # works when no browser is open (specs/teams-schedules, "Harmonogram należy do
        # operatora, który go zapisał"). The module calls nothing with this identity;
        # it is a label the owner-scoped queries filter on, not a credential.
        sa.Column("owner_principal", sa.Text(), nullable=False),
        *_revision_selection_columns("schedules"),
        sa.Column("cron_expression", sa.Text(), nullable=False),
        # Claimed with `UPDATE … WHERE next_fire_at <= now() RETURNING` (design.md,
        # "Wyzwolenie przejmowane w bazie, nie posiadane przez proces") — two processes
        # racing this statement give exactly one winner, which is what makes a fire
        # during a deployment single rather than double.
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
        # The condition, expressed as a call to a tool this module already has a
        # session for — never a locally computed indicator (specs/teams-triggers,
        # "Warunek jest czytany narzędziami serwera narzędzi"). `field_path` reads one
        # value out of that call's JSON result; `arguments` is what the tool needs
        # to answer at all (an instrument, a resolution, whatever that tool takes).
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
        # NULL is a third value, not "false" — the tool server being unreachable is not
        # the same fact as the condition being unmet (specs/teams-triggers,
        # "Niedostępność serwera narzędzi to nie jest niespełniony warunek"), and this
        # column is what the edge-detection in `next_check_at`'s claim compares against.
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
        # Names the reason a fire started nothing: a previous run still working, the
        # team's daily ceiling, a revision that no longer runs, or the tool server
        # being unreachable (specs/teams-schedules, "Wyzwolenie bez przebiegu zostawia
        # zapisany powód"). Required whenever `outcome` is not `started`.
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "run_id",
            sa.BigInteger(),
            sa.ForeignKey("runs.id", name="schedule_fires_run_id_fkey"),
            nullable=True,
        ),
        # How many due fires were collapsed into this one after the module was not
        # running to see them (specs/teams-schedules, "Pominięte wyzwolenia zwijają się
        # do jednego") — 0 for the ordinary case of a schedule that was never behind.
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
