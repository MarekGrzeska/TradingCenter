"""The archive: posts with the one reading a model has of each, the bill for those readings, and
what collection is currently doing per source.

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
    # Identity is the pair, never `external_id` alone: two sources are free to number their posts
    # the same way, and a second source is a file here rather than a rewrite.
    #
    # The reading lives in these columns rather than in a table of its own, and is overwritten when
    # the model or the prompt changes: the history is the post, not what a model thought of it.
    op.execute(
        """
        CREATE TABLE posts (
            id                  bigserial PRIMARY KEY,
            source              text NOT NULL,
            external_id         text NOT NULL,
            author              text NOT NULL,
            content             text NOT NULL,
            url                 text,
            is_repost           boolean NOT NULL DEFAULT false,
            published_at        timestamptz NOT NULL,
            fetched_at          timestamptz NOT NULL DEFAULT now(),
            translated_content  text,
            translated_model    text,
            translated_at       timestamptz,
            topics              text[],
            impact_score        smallint,
            analysed_model      text,
            analysed_at         timestamptz,
            UNIQUE (source, external_id),
            CONSTRAINT posts_impact_score_is_one_to_ten
                CHECK (impact_score IS NULL OR (impact_score BETWEEN 1 AND 10)),
            -- A reading without its stamp is an opinion this module would be presenting as its own.
            CONSTRAINT posts_readings_are_stamped CHECK (
                (translated_content IS NULL)
                    = (translated_model IS NULL AND translated_at IS NULL)
                AND (impact_score IS NULL) = (analysed_model IS NULL AND analysed_at IS NULL)
            )
        )
        """
    )
    # The window read every screen and every tool makes.
    op.execute("CREATE INDEX posts_published_idx ON posts (published_at DESC)")
    # And the same window narrowed by score, which is the question the operator actually asks.
    op.execute(
        "CREATE INDEX posts_impact_idx ON posts (impact_score DESC NULLS LAST, published_at DESC)"
    )
    op.execute("CREATE INDEX posts_source_published_idx ON posts (source, published_at DESC)")
    # `topics` is filtered by containment, which a btree cannot serve.
    op.execute("CREATE INDEX posts_topics_idx ON posts USING gin (topics)")

    # Survives the overwrite above, and that is the point: the money was spent on the reading that
    # no longer stands as much as on the one that does.
    op.execute(
        """
        CREATE TABLE model_usage (
            id             bigserial PRIMARY KEY,
            post_id        bigint NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
            operation      text NOT NULL,
            model          text NOT NULL,
            input_tokens   integer NOT NULL DEFAULT 0,
            output_tokens  integer NOT NULL DEFAULT 0,
            created_at     timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT model_usage_names_its_job
                CHECK (operation IN ('translation', 'analysis'))
        )
        """
    )
    op.execute("CREATE INDEX model_usage_post_idx ON model_usage (post_id, created_at)")

    # Silence in the data reads exactly like silence from the source without this table.
    # `collecting_since` is what makes an archive that starts on a known day different from one
    # that starts wherever the first pass happened to reach.
    op.execute(
        """
        CREATE TABLE collection_state (
            source                text PRIMARY KEY,
            collecting_since      timestamptz NOT NULL DEFAULT now(),
            last_success_at       timestamptz,
            last_failure_at       timestamptz,
            last_failure_reason   text,
            consecutive_failures  integer NOT NULL DEFAULT 0
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE collection_state")
    op.execute("DROP TABLE model_usage")
    op.execute("DROP TABLE posts")
