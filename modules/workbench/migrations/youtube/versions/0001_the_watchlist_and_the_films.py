"""The archive: what is followed, the films it yields, what was said in them, what a model made of it, what each provider
has been asked for and whether it lets us in.

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
    # The watch list. Removing a row must not take a film with it, so nothing below references these tables: a film is
    # the archive, a channel is only why we looked.
    op.execute(
        """
        CREATE TABLE channels (
            channel_id           text PRIMARY KEY,
            title                text NOT NULL,
            handle               text,
            uploads_playlist_id  text,
            language             text NOT NULL DEFAULT '',
            profile              text NOT NULL DEFAULT 'market',
            alert_rule           text NOT NULL DEFAULT 'threshold',
            active               boolean NOT NULL DEFAULT true,
            added_by             text NOT NULL,
            added_at             timestamptz NOT NULL DEFAULT now(),
            last_discovery_at    timestamptz,
            CONSTRAINT channels_alert_rule_is_known
                CHECK (alert_rule IN ('always', 'threshold', 'never')),
            CONSTRAINT channels_added_by_is_known CHECK (added_by IN ('operator', 'agent'))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE topics (
            id                   bigserial PRIMARY KEY,
            phrase               text NOT NULL,
            language             text NOT NULL DEFAULT '',
            interval_minutes     integer NOT NULL,
            max_videos_per_run   integer NOT NULL,
            profile              text NOT NULL DEFAULT 'market',
            alert_rule           text NOT NULL DEFAULT 'threshold',
            active               boolean NOT NULL DEFAULT true,
            added_by             text NOT NULL,
            added_at             timestamptz NOT NULL DEFAULT now(),
            last_run_at          timestamptz,
            CONSTRAINT topics_interval_is_positive CHECK (interval_minutes > 0),
            CONSTRAINT topics_run_limit_is_positive CHECK (max_videos_per_run > 0),
            CONSTRAINT topics_alert_rule_is_known
                CHECK (alert_rule IN ('always', 'threshold', 'never')),
            CONSTRAINT topics_added_by_is_known CHECK (added_by IN ('operator', 'agent'))
        )
        """
    )
    # The same phrase in another spelling of the case is the same topic.
    op.execute("CREATE UNIQUE INDEX topics_phrase_idx ON topics (lower(phrase), language)")

    # The film's identity is YouTube's own id, whichever door it came in by. `origins` says which: `channel:UC…`,
    # `topic:7`, `manual`. `state` is what the loop reads; a film that is `gave_up` or `skipped` is never picked up.
    op.execute(
        """
        CREATE TABLE videos (
            video_id           text PRIMARY KEY,
            channel_id         text,
            channel_title      text NOT NULL DEFAULT '',
            title              text NOT NULL,
            published_at       timestamptz NOT NULL,
            duration_seconds   integer,
            live_status        text NOT NULL DEFAULT 'none',
            origins            text[] NOT NULL,
            profile            text NOT NULL DEFAULT 'market',
            alert_rule         text NOT NULL DEFAULT 'threshold',
            state              text NOT NULL DEFAULT 'discovered',
            skip_reason        text,
            attempts           integer NOT NULL DEFAULT 0,
            next_attempt_at    timestamptz,
            reading_failures   integer NOT NULL DEFAULT 0,
            -- A provider that takes a long film answers later, by job: which provider, and which job.
            job_provider       text,
            job_id             text,
            simulated          boolean NOT NULL DEFAULT false,
            discovered_at      timestamptz NOT NULL DEFAULT now(),
            notified_at        timestamptz,
            CONSTRAINT videos_state_is_known CHECK (state IN (
                'discovered', 'no_transcript', 'transcribed', 'analysed',
                'notified', 'quiet', 'gave_up', 'skipped'
            )),
            CONSTRAINT videos_live_status_is_known
                CHECK (live_status IN ('none', 'live', 'upcoming')),
            CONSTRAINT videos_alert_rule_is_known
                CHECK (alert_rule IN ('always', 'threshold', 'never')),
            -- A skipped film that does not say why is a film nobody can account for.
            CONSTRAINT videos_skip_says_why CHECK (state <> 'skipped' OR skip_reason IS NOT NULL)
        )
        """
    )
    # The loop's queue: only the states it still has work in, so a year of `quiet` films is not in the index.
    op.execute(
        """
        CREATE INDEX videos_queue_idx ON videos (state, next_attempt_at)
            WHERE state IN ('discovered', 'no_transcript', 'transcribed', 'analysed')
        """
    )
    # The window every screen and every tool reads.
    op.execute("CREATE INDEX videos_published_idx ON videos (published_at DESC)")
    op.execute("CREATE INDEX videos_channel_published_idx ON videos (channel_id, published_at DESC)")

    # The text is apart from the film so that neither the queue nor a list ever reads it: a transcript is tens of
    # kilobytes, and only two paths want it.
    op.execute(
        """
        CREATE TABLE transcripts (
            video_id    text PRIMARY KEY REFERENCES videos(video_id) ON DELETE CASCADE,
            content     text NOT NULL,
            language    text NOT NULL,
            provider    text NOT NULL,
            automatic   boolean NOT NULL,
            simulated   boolean NOT NULL DEFAULT false,
            fetched_at  timestamptz NOT NULL DEFAULT now()
        )
        """
    )

    # A reading per film and profile, overwritten when the model or the prompt changes: the history is the film, not
    # what a model thought of it. `impact_score` and `instruments` are lifted out of the document so a screen and a
    # tool can filter on them without opening it.
    op.execute(
        """
        CREATE TABLE readings (
            video_id      text NOT NULL REFERENCES videos(video_id) ON DELETE CASCADE,
            profile       text NOT NULL,
            result        jsonb NOT NULL,
            impact_score  smallint NOT NULL,
            instruments   text[] NOT NULL DEFAULT '{}',
            model         text NOT NULL,
            simulated     boolean NOT NULL DEFAULT false,
            analysed_at   timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (video_id, profile),
            CONSTRAINT readings_impact_score_is_one_to_ten CHECK (impact_score BETWEEN 1 AND 10)
        )
        """
    )
    op.execute("CREATE INDEX readings_impact_idx ON readings (impact_score DESC, analysed_at DESC)")
    op.execute("CREATE INDEX readings_instruments_idx ON readings USING gin (instruments)")

    # What each provider has been asked for, per day and in its own unit — API units, credits, tokens. Kept when the
    # content is gone: the money was spent whether or not the film still stands. The day is UTC.
    op.execute(
        """
        CREATE TABLE usage (
            day       date NOT NULL,
            provider  text NOT NULL,
            unit      text NOT NULL,
            amount    bigint NOT NULL DEFAULT 0,
            PRIMARY KEY (day, provider, unit),
            CONSTRAINT usage_amount_is_not_negative CHECK (amount >= 0)
        )
        """
    )

    # Whether a provider lets us in, apart from whether a film has captions: from a home address the fetch works and
    # from a datacenter it may be refused wholesale, and without this row that reads as a run of films with no captions.
    op.execute(
        """
        CREATE TABLE provider_state (
            provider         text PRIMARY KEY,
            last_ok_at       timestamptz,
            last_blocked_at  timestamptz,
            blocked_reason   text
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE provider_state")
    op.execute("DROP TABLE usage")
    op.execute("DROP TABLE readings")
    op.execute("DROP TABLE transcripts")
    op.execute("DROP TABLE videos")
    op.execute("DROP TABLE topics")
    op.execute("DROP TABLE channels")
