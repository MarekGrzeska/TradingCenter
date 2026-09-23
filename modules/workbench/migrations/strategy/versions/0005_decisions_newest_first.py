"""An index in the order the terminal reads decisions: newest first, every minute, `LIMIT 100`. Without it each
read scanned and sorted the whole table, which only grows.

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
    op.execute("CREATE INDEX decisions_newest_first ON decisions (as_of DESC, id DESC)")


def downgrade() -> None:
    op.execute("DROP INDEX decisions_newest_first")
