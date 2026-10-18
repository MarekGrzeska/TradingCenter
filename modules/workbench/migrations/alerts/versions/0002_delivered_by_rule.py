"""What a rule has told in the last hour, without reading everything it ever told.

The cap on a rule's messages counts its deliveries since an hour ago, once per message sent. Measured on 300 000 fires
over 100 rules, 3 000 each: 3 008 pages through `fires_one_per_event` to find 36 rows. With this index the count reads
the hour and nothing else.

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX fires_delivered_by_rule ON fires (rule_id, delivered_at) WHERE state = 'delivered'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS fires_delivered_by_rule")
