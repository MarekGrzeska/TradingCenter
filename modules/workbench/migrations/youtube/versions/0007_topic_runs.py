"""Every attempt to search a topic is written down with its report. No key to `topics`: the list is why a topic was searched,
not what is kept, so a run outlives the topic taken off it and carries the phrase it searched for.

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
    op.execute(
        """
        CREATE TABLE topic_runs (
            id                 bigserial PRIMARY KEY,
            topic_id           bigint NOT NULL,
            phrase             text NOT NULL,
            ran_at             timestamptz NOT NULL,
            outcome            text NOT NULL,
            results            integer NOT NULL DEFAULT 0,
            known              integer NOT NULL DEFAULT 0,
            out_of_bounds      integer NOT NULL DEFAULT 0,
            proposed           integer NOT NULL DEFAULT 0,
            rejected           integer NOT NULL DEFAULT 0,
            unscreened         integer NOT NULL DEFAULT 0,
            unscreened_reason  text,
            error              text,
            CONSTRAINT topic_runs_outcome_is_known CHECK (outcome IN ('found', 'nothing_new', 'failed', 'skipped')),
            CONSTRAINT topic_runs_unscreened_reason_is_known
                CHECK (unscreened_reason IS NULL OR unscreened_reason IN
                       ('no_model', 'day_spent', 'unusable', 'failed', 'no_verdict')),
            -- A run that did not happen and does not say why is the silence this table exists to end.
            CONSTRAINT topic_runs_failure_says_why CHECK (outcome NOT IN ('failed', 'skipped') OR error IS NOT NULL)
        )
        """
    )
    # A topic's own history, newest first; and the retention sweep and the all-topics list, which read by time alone.
    op.execute("CREATE INDEX topic_runs_topic_idx ON topic_runs (topic_id, ran_at DESC, id DESC)")
    op.execute("CREATE INDEX topic_runs_ran_at_idx ON topic_runs (ran_at)")


def downgrade() -> None:
    op.execute("DROP TABLE topic_runs")
