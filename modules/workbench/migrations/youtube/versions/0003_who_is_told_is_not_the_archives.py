"""Who is told about a film is not the archive's to say.

The alert rule of a channel, of a topic and of a film (`always`, `threshold`, `never`) was converted into rules of the alerts
package by the conversion that ran at its first start, and nothing reads the columns any more. Not reversible in the data:
`downgrade` brings back the columns at their default, not what the operator had set.

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("channels", "topics", "videos")


def upgrade() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {table}_alert_rule_is_known")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS alert_rule")


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ADD COLUMN alert_rule text NOT NULL DEFAULT 'threshold'")
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {table}_alert_rule_is_known "
            "CHECK (alert_rule IN ('always', 'threshold', 'never'))"
        )
