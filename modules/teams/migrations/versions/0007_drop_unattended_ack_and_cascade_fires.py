"""Two changes to the schedule tables, and they arrive together because both are the same
decision: a schedule is a thing the operator manages, not a thing they consent to once.

- **`unattended_ack` goes.** It was checked in one place out of two: `validation.py` ran
  it when a schedule was saved, and the firing path never asked at all — so a schedule
  saved legally over a read-only revision kept firing by itself after the operator added
  an order-placing tool to the team. Closing that would have meant checking at every fire,
  which is a schedule stopping itself at three in the morning over a consent nobody is
  awake to give. What it did stop was the honest route: a schedule asked for in the chat,
  refused by naming a field the chat cannot fill (specs/teams-schedules, the removed
  requirement, and its `Migration` note for what still stops an irreversible order).

- **`schedule_fires` gets `ON DELETE CASCADE`.** A schedule can now be deleted, and its
  fire history cannot outlive it: the `CHECK` from `0005` demands that a fire row name
  exactly one of a schedule or a trigger, so there is no orphan state to move it into.
  Without the cascade the delete would simply fail against any schedule that ever fired,
  which is every schedule worth deleting.

Runs are untouched by both, and by construction rather than by care: `runs` has no column
pointing at a schedule — it is `schedule_fires.run_id` that points at a run. Deleting a
schedule takes its log, never the work it started, so what a run cost and what it traded
survives the schedule that ordered it.

`downgrade` puts the column back with `false` in every row. That is the honest restoration
and it is not the state we left: after it, every existing schedule would be refused at its
next *edit* — though still not at its next fire, which was the hole all along.

Revision ID: 0007
Revises: 0006
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FIRE_KEYS = (
    ("schedule_fires_schedule_id_fkey", "schedule_id", "schedules"),
    ("schedule_fires_trigger_id_fkey", "trigger_id", "triggers"),
)


def _recreate_fire_keys(ondelete: str | None) -> None:
    for name, column, target in _FIRE_KEYS:
        op.drop_constraint(name, "schedule_fires", type_="foreignkey")
        op.create_foreign_key(
            name, "schedule_fires", target, [column], ["id"], ondelete=ondelete
        )


def upgrade() -> None:
    op.drop_column("schedules", "unattended_ack")
    op.drop_column("triggers", "unattended_ack")
    _recreate_fire_keys("CASCADE")


def downgrade() -> None:
    _recreate_fire_keys(None)
    for table in ("schedules", "triggers"):
        op.add_column(
            table,
            sa.Column(
                "unattended_ack",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
