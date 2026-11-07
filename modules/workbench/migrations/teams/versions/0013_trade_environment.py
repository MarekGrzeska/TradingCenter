"""A trade names the environment it went to, beside the account.

`demo` for every trade before this column: the live account did not exist for this module until then.

Revision ID: 0013
Revises: 0012
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE trades ADD COLUMN environment text NOT NULL DEFAULT 'demo'")


def downgrade() -> None:
    op.execute("ALTER TABLE trades DROP COLUMN IF EXISTS environment")
