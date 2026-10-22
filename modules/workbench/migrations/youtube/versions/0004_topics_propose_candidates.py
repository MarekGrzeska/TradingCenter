"""A topic proposes films instead of feeding them to the archive. `candidates` holds what a topic's search found and a model
screened by its metadata; `ignored_channels` holds the channels the operator does not want proposed. A topic no longer reads
anything, so it loses its prompt. Films a topic found before stay in `videos` with their origin and their readings.

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE candidates (
            video_id          text PRIMARY KEY,
            topic_id          bigint REFERENCES topics(id) ON DELETE SET NULL,
            phrase            text NOT NULL,
            channel_id        text,
            channel_title     text NOT NULL,
            title             text NOT NULL,
            published_at      timestamptz NOT NULL,
            duration_seconds  integer,
            simulated         boolean NOT NULL DEFAULT false,
            found_at          timestamptz NOT NULL DEFAULT now(),
            verdict           text NOT NULL,
            reason            text,
            screened_by       text,
            decision          text,
            decided_at        timestamptz,
            CONSTRAINT candidates_verdict_is_known CHECK (verdict IN ('proposed', 'rejected', 'unscreened')),
            CONSTRAINT candidates_decision_is_known
                CHECK (decision IN ('dismissed', 'analysed', 'channel_followed', 'channel_ignored')),
            CONSTRAINT candidates_decision_has_its_moment CHECK ((decision IS NULL) = (decided_at IS NULL))
        )
        """
    )
    # The default list is the proposed ones nobody has decided about, newest first in either order, so that is what is indexed.
    op.execute(
        "CREATE INDEX candidates_open_found_idx ON candidates (found_at DESC) "
        "WHERE decision IS NULL AND verdict <> 'rejected'"
    )
    op.execute(
        "CREATE INDEX candidates_open_published_idx ON candidates (published_at DESC) "
        "WHERE decision IS NULL AND verdict <> 'rejected'"
    )
    op.execute("CREATE INDEX candidates_channel_idx ON candidates (channel_id) WHERE decision IS NULL")
    op.execute(
        """
        CREATE TABLE ignored_channels (
            channel_id     text PRIMARY KEY,
            channel_title  text NOT NULL,
            ignored_at     timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("ALTER TABLE topics DROP COLUMN prompt_id")


def downgrade() -> None:
    """The schema, not the candidates: they have no place in the older one. Every topic goes back to the seeded prompt."""
    bind = op.get_bind()
    seeded = bind.execute(sa.text("SELECT id FROM prompts WHERE seeded")).scalar_one()
    op.execute("ALTER TABLE topics ADD COLUMN prompt_id bigint REFERENCES prompts(id)")
    bind.execute(sa.text("UPDATE topics SET prompt_id = :id"), {"id": seeded})
    op.execute("ALTER TABLE topics ALTER COLUMN prompt_id SET NOT NULL")
    op.execute("DROP TABLE ignored_channels")
    op.execute("DROP TABLE candidates")
