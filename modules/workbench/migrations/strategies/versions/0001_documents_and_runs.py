"""Strategies as documents, their revisions, every run made of one, and every trade a run produced.

Revision ID: 0001
Revises:
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # No delete anywhere in this package: a strategy is archived, so the count of what was tried stays true.
    op.execute(
        """
        CREATE TABLE strategies (
            id           bigserial PRIMARY KEY,
            name         text NOT NULL,
            created_at   timestamptz NOT NULL DEFAULT now(),
            archived_at  timestamptz
        )
        """
    )
    # A revision is never updated; the next save is the next row. `schema_version` is the language the document was
    # written in, so a later engine still knows how to read it.
    op.execute(
        """
        CREATE TABLE strategy_revisions (
            strategy_id     bigint NOT NULL REFERENCES strategies (id),
            n               integer NOT NULL CHECK (n >= 1),
            document        jsonb NOT NULL,
            content_hash    text NOT NULL,
            schema_version  integer NOT NULL,
            author          text NOT NULL CHECK (author IN ('operator', 'agent')),
            created_at      timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (strategy_id, n)
        )
        """
    )
    # `request` is everything the run was asked with — parameters, costs, range, capital, seed — and `provenance`
    # everything it read, so two reports that differ can say why.
    op.execute(
        """
        CREATE TABLE runs (
            id              bigserial PRIMARY KEY,
            strategy_id     bigint NOT NULL,
            revision        integer NOT NULL,
            request         jsonb NOT NULL,
            status          text NOT NULL DEFAULT 'queued'
                            CHECK (status IN ('queued', 'running', 'done', 'failed', 'cancelled')),
            reason          text,
            engine_version  integer,
            queued_at       timestamptz NOT NULL DEFAULT now(),
            started_at      timestamptz,
            finished_at     timestamptz,
            report          jsonb,
            provenance      jsonb,
            FOREIGN KEY (strategy_id, revision) REFERENCES strategy_revisions (strategy_id, n)
        )
        """
    )
    op.execute("CREATE INDEX runs_by_strategy ON runs (strategy_id, queued_at DESC)")
    # What the queue looks for, and what a restart marks as interrupted: a handful of rows, never the whole history.
    op.execute("CREATE INDEX runs_waiting ON runs (queued_at) WHERE status IN ('queued', 'running')")

    # A table rather than a field of the report: a scalping run over a year is thousands of trades, read a page at a time.
    op.execute(
        """
        CREATE TABLE run_trades (
            run_id          bigint NOT NULL REFERENCES runs (id),
            seq             integer NOT NULL,
            side            text NOT NULL CHECK (side IN ('long', 'short')),
            entry_time      timestamptz NOT NULL,
            entry_price     double precision NOT NULL,
            exit_time       timestamptz NOT NULL,
            exit_price      double precision NOT NULL,
            units           double precision NOT NULL,
            initial_stop    double precision NOT NULL,
            result_r        double precision NOT NULL,
            result_money    double precision NOT NULL,
            costs           jsonb NOT NULL,
            exit_reason     text NOT NULL
                            CHECK (exit_reason IN ('stop', 'target', 'trail', 'when', 'max_bars', 'end_of_range')),
            pessimistic     boolean NOT NULL,
            PRIMARY KEY (run_id, seq)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE run_trades")
    op.execute("DROP TABLE runs")
    op.execute("DROP TABLE strategy_revisions")
    op.execute("DROP TABLE strategies")
