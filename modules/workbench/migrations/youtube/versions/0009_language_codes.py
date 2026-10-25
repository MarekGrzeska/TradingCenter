"""Languages written as names before the watch list checked them — the agent's "Polish" and "English" — become the codes the
Data API takes. Every search of such a topic was answered 400, so its hold from those refusals is lifted with it.

Revision ID: 0009
Revises: 0008
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NAMES = {"polish": "pl", "english": "en", "german": "de", "french": "fr", "spanish": "es", "russian": "ru", "ukrainian": "uk"}


def upgrade() -> None:
    for name, code in _NAMES.items():
        # A topic already kept under the code as well would collide on (lower(phrase), language); it stays as it was.
        op.execute(
            f"""
            UPDATE topics t SET language = '{code}', retry_at = NULL
             WHERE lower(t.language) = '{name}'
               AND NOT EXISTS (
                   SELECT 1 FROM topics o WHERE lower(o.phrase) = lower(t.phrase) AND o.language = '{code}'
               )
            """
        )
        op.execute(f"UPDATE channels SET language = '{code}' WHERE lower(language) = '{name}'")


def downgrade() -> None:
    pass
