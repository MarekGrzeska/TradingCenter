"""Definitions and their revisions — the half of a strategy that used to be only code. Additive
throughout: `NULL` in the four new columns means exactly what it says, and is not missing data.

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The name and identity of a clicked strategy. `strategy_id` is a plain text id from the same
    # namespace the coded entries use, so everything downstream keeps working on one kind of key.
    op.create_table(
        "strategy_definitions",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("strategy_id", sa.Text, nullable=False, unique=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=sa.text("''")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    # Append-only, exactly like `parameter_sets`: a decision names the revision it was computed under,
    # and answering "what decided this" a month later requires that revision to read as it read then.
    op.create_table(
        "strategy_revisions",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column(
            "definition_id",
            sa.BigInteger,
            sa.ForeignKey("strategy_definitions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer, nullable=False),
        # The whole rule as one blob. Not shredded into node rows: a tree in tables is a tree nobody
        # can read in a query, and a kept revision has to be readable exactly as written.
        sa.Column("definition", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("definition_id", "version", name="strategy_revisions_version"),
    )

    # A parameter set belongs to a revision, not to a strategy: a value inside its range under one
    # revision may be outside it under the next. Nullable, because a coded entry has no revision.
    op.add_column(
        "parameter_sets",
        sa.Column(
            "strategy_revision_id",
            sa.BigInteger,
            sa.ForeignKey("strategy_revisions.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )

    # The watch pins its revision. Saving a newer one MUST NOT change what a running watch computes —
    # a rule swapped underfoot produces decisions that look comparable and are not.
    op.add_column(
        "watches",
        sa.Column(
            "strategy_revision_id",
            sa.BigInteger,
            sa.ForeignKey("strategy_revisions.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )

    # The other half of provenance. With the parameter version alone, "why did this enter"
    # has the numbers and not the rule that weighed them.
    op.add_column(
        "decisions",
        sa.Column(
            "strategy_revision_id",
            sa.BigInteger,
            sa.ForeignKey("strategy_revisions.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )

    op.add_column(
        "backtest_runs",
        sa.Column(
            "strategy_revision_id",
            sa.BigInteger,
            sa.ForeignKey("strategy_revisions.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("backtest_runs", "strategy_revision_id")
    op.drop_column("decisions", "strategy_revision_id")
    op.drop_column("watches", "strategy_revision_id")
    op.drop_column("parameter_sets", "strategy_revision_id")
    op.drop_table("strategy_revisions")
    op.drop_table("strategy_definitions")
