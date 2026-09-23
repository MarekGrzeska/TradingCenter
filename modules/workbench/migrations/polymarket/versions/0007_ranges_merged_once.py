"""Every collected range merged with those it touches, once. Ticks have merged since 0004's day, but the
5.2 million ranges written before it stayed one per tick: 848 MB on 23 September 2026, for what merges
into a few thousand rows. `TRUNCATE` rather than `DELETE`, so the space comes back without a VACUUM FULL.

The lock lets reads through and holds the previous container's sampler until this commits — its ranges
would otherwise land between the read and the truncate and be lost. 4 s for 5.2 million rows on one core.

Revision ID: 0007
Revises: 0006
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("SET LOCAL work_mem = '64MB'")
    op.execute("LOCK TABLE collected_ranges IN EXCLUSIVE MODE")
    # An island starts where a range begins after everything before it has ended — the same "touching"
    # `store.record_collected_many` merges on, so what it would have made is what this makes.
    op.execute(
        """
        CREATE TEMP TABLE merged_ranges ON COMMIT DROP AS
        WITH ordered AS (
            SELECT outcome_id, starts_at, ends_at,
                   max(ends_at) OVER (PARTITION BY outcome_id ORDER BY starts_at, ends_at
                                      ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS reach
              FROM collected_ranges
        ),
        islands AS (
            SELECT outcome_id, starts_at, ends_at,
                   count(*) FILTER (WHERE reach IS NULL OR starts_at > reach)
                       OVER (PARTITION BY outcome_id ORDER BY starts_at, ends_at
                             ROWS UNBOUNDED PRECEDING) AS island
              FROM ordered
        )
        SELECT outcome_id, min(starts_at) AS starts_at, max(ends_at) AS ends_at
          FROM islands
         GROUP BY outcome_id, island
        """
    )
    op.execute("TRUNCATE collected_ranges")
    op.execute(
        "INSERT INTO collected_ranges (outcome_id, starts_at, ends_at) "
        "SELECT outcome_id, starts_at, ends_at FROM merged_ranges"
    )


def downgrade() -> None:
    # Merged ranges answer every coverage question the unmerged ones did; there is nothing to split back.
    pass
