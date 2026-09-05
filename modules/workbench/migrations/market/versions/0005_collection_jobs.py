"""Collection jobs — a durable record of what backfill was asked for, and how it went.

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RESOLUTIONS = (
    "MINUTE",
    "MINUTE_5",
    "MINUTE_15",
    "MINUTE_30",
    "HOUR",
    "HOUR_4",
    "DAY",
    "WEEK",
)

# One period's length, spelled out rather than imported — see 0001's note on why a
# migration carries its own copy instead of reaching into `market_data.periods`.
PERIOD_SECONDS: dict[str, int] = {
    "MINUTE": 60,
    "MINUTE_5": 300,
    "MINUTE_15": 900,
    "MINUTE_30": 1_800,
    "HOUR": 3_600,
    "HOUR_4": 14_400,
    "DAY": 86_400,
    "WEEK": 604_800,
}

# Mirrors `Settings.default_backfill_bars`. A pair tracked before this column existed reached back
# this many candles on its first fill, so this gives it a `collect_from` that says exactly that.
DEFAULT_BACKFILL_BARS = 5_000

# Chunk states. `interrupted` is reached only from `pending` or `running`, and only by the module's
# own startup: no runner survives a restart.
CHUNK_STATES = ("pending", "running", "done", "failed", "skipped", "interrupted")


def _in_list(column: str, values: Sequence[str]) -> str:
    return f"{column} IN (" + ", ".join(f"'{value}'" for value in values) + ")"


def upgrade() -> None:
    op.create_table(
        "collection_jobs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # What the operator asked for, before any per-pair clipping. A chunk's own window is the
        # authoritative one; this is kept beside it so a job can say requested versus reachable.
        sa.Column("requested_from", sa.TIMESTAMP(timezone=True), nullable=False),
        # Bumped by a retry. On the job rather than inferred from its chunks: "how many times has
        # this been retried" is a fact about the job, not a scan of every chunk.
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint("attempt > 0", name="collection_jobs_attempt_positive"),
    )

    op.create_table(
        "collection_job_chunks",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "job_id",
            sa.BigInteger(),
            sa.ForeignKey("collection_jobs.id", name="collection_job_chunks_job_id_fkey"),
            nullable=False,
        ),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("resolution", sa.Text(), nullable=False),
        # The window this one chunk covers — one gateway request's worth. Half-open in spirit,
        # matching every other range in this module.
        sa.Column("chunk_start", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("chunk_end", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("state", sa.Text(), nullable=False, server_default="pending"),
        # Which attempt of the *job* last touched this chunk. A chunk done on attempt 1 stays done
        # through a later retry of its siblings, which is what lets a retry skip it.
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("candles_written", sa.Integer(), nullable=False, server_default="0"),
        # Provider calls the gateway made behind this one chunk's request — the gateway
        # pages internally, and this is what that paging cost.
        sa.Column("requests", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure", sa.Text(), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint("chunk_end >= chunk_start", name="collection_job_chunks_not_inverted"),
        sa.CheckConstraint("attempt > 0", name="collection_job_chunks_attempt_positive"),
        sa.CheckConstraint(_in_list("state", CHUNK_STATES), name="collection_job_chunks_state_known"),
        sa.CheckConstraint(
            _in_list("resolution", RESOLUTIONS), name="collection_job_chunks_resolution_known"
        ),
        # A pair this names must be one tracking has decided on — untracking flips a row rather than
        # deleting it, so this holds even for a pair stopped after its job ran.
        sa.ForeignKeyConstraint(
            ["symbol", "resolution"],
            ["tracked_pairs.symbol", "tracked_pairs.resolution"],
            name="collection_job_chunks_pair_fkey",
        ),
    )
    # What the runner scans for work, and what a job's own detail read groups by.
    op.create_index("collection_job_chunks_job_id_idx", "collection_job_chunks", ["job_id"])
    op.create_index(
        "collection_job_chunks_pair_idx", "collection_job_chunks", ["symbol", "resolution"]
    )
    # The runner's queue: chunks not yet settled, oldest job first. Partial, because a
    # settled chunk never needs to be found this way again.
    op.create_index(
        "collection_job_chunks_pending_idx",
        "collection_job_chunks",
        ["job_id", "id"],
        postgresql_where=sa.text("state = 'pending'"),
    )

    op.add_column(
        "tracked_pairs", sa.Column("collect_from", sa.TIMESTAMP(timezone=True), nullable=True)
    )
    conn = op.get_bind()
    cases = " ".join(
        f"WHEN '{resolution}' THEN added_at - INTERVAL '{seconds * DEFAULT_BACKFILL_BARS} seconds'"
        for resolution, seconds in PERIOD_SECONDS.items()
    )
    conn.execute(
        sa.text(
            f"UPDATE tracked_pairs SET collect_from = CASE resolution {cases} END "
            "WHERE collect_from IS NULL"
        )
    )
    op.alter_column("tracked_pairs", "collect_from", nullable=False)


def downgrade() -> None:
    op.drop_column("tracked_pairs", "collect_from")
    op.drop_index("collection_job_chunks_pending_idx", table_name="collection_job_chunks")
    op.drop_index("collection_job_chunks_pair_idx", table_name="collection_job_chunks")
    op.drop_index("collection_job_chunks_job_id_idx", table_name="collection_job_chunks")
    op.drop_table("collection_job_chunks")
    op.drop_table("collection_jobs")
