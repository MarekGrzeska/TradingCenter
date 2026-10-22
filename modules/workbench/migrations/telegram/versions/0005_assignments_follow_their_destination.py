"""Nothing reads the assignments any more, so they must not hold a destination back.

Who is told what is decided by rules in the alerts package, which name a destination. The two old tables stay one release
longer, until the conversion is known to have run in production (`alerts-package`, group 11); until then a leftover
assignment must not make removing a destination fail now that the route that refused it first is gone.

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE assignments DROP CONSTRAINT assignments_destination_id_fkey")
    op.execute(
        "ALTER TABLE assignments ADD CONSTRAINT assignments_destination_id_fkey "
        "FOREIGN KEY (destination_id) REFERENCES destinations(id) ON DELETE CASCADE"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE assignments DROP CONSTRAINT assignments_destination_id_fkey")
    op.execute(
        "ALTER TABLE assignments ADD CONSTRAINT assignments_destination_id_fkey "
        "FOREIGN KEY (destination_id) REFERENCES destinations(id) ON DELETE RESTRICT"
    )
