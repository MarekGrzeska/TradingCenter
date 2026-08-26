"""Two changes arriving together because both are one decision: a schedule is managed, not consented to once.
`unattended_ack` was checked at save and never at a fire; the cascade follows a schedule now being deletable.

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
