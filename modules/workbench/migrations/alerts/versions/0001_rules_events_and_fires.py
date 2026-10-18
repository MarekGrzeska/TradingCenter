"""Rules, the events that can trigger them, the looks at a value, and every time one went off.

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
    # What the packages announced they can say. The schema is the contract a rule's filter is checked against, so a
    # rule cannot name an attribute nobody sends.
    op.execute(
        """
        CREATE TABLE event_types (
            name                text PRIMARY KEY,
            description         text NOT NULL,
            schema              jsonb NOT NULL,
            announced_by        text,
            first_announced_at  timestamptz NOT NULL DEFAULT now(),
            last_announced_at   timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    # `(type, source_key)` is the idempotency of a publication: a producer retries until it hears yes, and the second
    # yes must not be a second alert.
    op.execute(
        """
        CREATE TABLE events (
            id           bigserial PRIMARY KEY,
            type         text NOT NULL REFERENCES event_types (name),
            source_key   text NOT NULL,
            attributes   jsonb NOT NULL,
            text         text NOT NULL,
            occurred_at  timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT events_one_per_source UNIQUE (type, source_key)
        )
        """
    )
    op.execute("CREATE INDEX events_occurred_at ON events (occurred_at)")

    # One table for both kinds of source. The columns of the kind a rule is not stay null, and the check says which are
    # which, so a half-filled rule cannot be stored.
    op.execute(
        """
        CREATE TABLE rules (
            id                     bigserial PRIMARY KEY,
            name                   text NOT NULL,
            kind                   text NOT NULL,
            destination            text NOT NULL,
            template               text NOT NULL,
            cooldown_seconds       integer NOT NULL,
            mode                   text NOT NULL,
            max_per_hour           integer,
            tool_name              text,
            arguments              jsonb,
            field_path             text,
            comparison             text,
            threshold              numeric,
            poll_interval_seconds  integer,
            event_type             text REFERENCES event_types (name),
            filter                 jsonb,
            enabled                boolean NOT NULL DEFAULT true,
            disabled_reason        text,
            defect                 text,
            next_check_at          timestamptz,
            last_result            boolean,
            last_known_result      boolean,
            last_checked_at        timestamptz,
            last_fired_at          timestamptz,
            throttle_notified_at   timestamptz,
            created_by             text NOT NULL,
            created_at             timestamptz NOT NULL DEFAULT now(),
            updated_at             timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT rules_kind_is_known CHECK (kind IN ('condition', 'event')),
            CONSTRAINT rules_mode_is_known CHECK (mode IN ('once', 'repeat')),
            CONSTRAINT rules_comparison_is_known
                CHECK (comparison IS NULL OR comparison IN ('gt', 'gte', 'lt', 'lte', 'eq')),
            CONSTRAINT rules_have_one_source CHECK (
                (kind = 'condition'
                    AND tool_name IS NOT NULL AND field_path IS NOT NULL AND comparison IS NOT NULL
                    AND threshold IS NOT NULL AND poll_interval_seconds IS NOT NULL
                    AND event_type IS NULL AND filter IS NULL)
                OR
                (kind = 'event'
                    AND event_type IS NOT NULL
                    AND tool_name IS NULL AND field_path IS NULL AND comparison IS NULL
                    AND threshold IS NULL AND poll_interval_seconds IS NULL)
            )
        )
        """
    )
    # The clock's claim: the rules that are due, and only those that can fire.
    op.execute(
        """
        CREATE INDEX rules_due ON rules (next_check_at)
         WHERE enabled AND kind = 'condition'
        """
    )
    op.execute("CREATE INDEX rules_by_event_type ON rules (event_type) WHERE enabled AND kind = 'event'")

    # What a look at a value found when it was not "no, still not": the tool could not be asked, refused, or the edge fell
    # inside the cool-down. A look that found nothing is a column on the rule, not a row — a rule looked at every half
    # minute would otherwise be thousands of rows a day saying the same thing.
    op.execute(
        """
        CREATE TABLE rule_checks (
            id          bigserial PRIMARY KEY,
            rule_id     bigint NOT NULL REFERENCES rules (id) ON DELETE CASCADE,
            checked_at  timestamptz NOT NULL DEFAULT now(),
            outcome     text NOT NULL,
            reason      text NOT NULL,
            CONSTRAINT rule_checks_outcome_is_known
                CHECK (outcome IN ('unavailable', 'refused', 'cooldown'))
        )
        """
    )
    op.execute("CREATE INDEX rule_checks_by_rule ON rule_checks (rule_id, checked_at DESC)")

    # Every time a rule went off, and what became of the message. Deleting an event leaves the fire: the text that was
    # sent is the record, and the event it came from was only ever the reason.
    op.execute(
        """
        CREATE TABLE fires (
            id               bigserial PRIMARY KEY,
            rule_id          bigint NOT NULL REFERENCES rules (id) ON DELETE CASCADE,
            event_id         bigint REFERENCES events (id) ON DELETE SET NULL,
            edge_at          timestamptz,
            state            text NOT NULL,
            reason           text,
            text             text NOT NULL,
            value            numeric,
            attempts         integer NOT NULL DEFAULT 0,
            next_attempt_at  timestamptz,
            created_at       timestamptz NOT NULL DEFAULT now(),
            delivered_at     timestamptz,
            CONSTRAINT fires_state_is_known
                CHECK (state IN ('pending', 'delivered', 'refused', 'abandoned', 'throttled', 'undeliverable')),
            CONSTRAINT fires_one_per_event UNIQUE (rule_id, event_id),
            CONSTRAINT fires_one_per_edge UNIQUE (rule_id, edge_at)
        )
        """
    )
    # The delivery claim, and the history a rule shows.
    op.execute("CREATE INDEX fires_due ON fires (next_attempt_at) WHERE state = 'pending'")
    op.execute("CREATE INDEX fires_by_rule ON fires (rule_id, created_at DESC)")

    # Tokens a draft cost, so the day's ceiling is counted here rather than trusted to the provider's dashboard.
    op.execute(
        """
        CREATE TABLE draft_usage (
            id             bigserial PRIMARY KEY,
            at             timestamptz NOT NULL DEFAULT now(),
            model          text NOT NULL,
            input_tokens   integer NOT NULL,
            output_tokens  integer NOT NULL
        )
        """
    )
    op.execute("CREATE INDEX draft_usage_at ON draft_usage (at)")

    # What has been done once and must not be done twice: the first start's conversion of the old assignments.
    op.execute(
        """
        CREATE TABLE migrations_done (
            name     text PRIMARY KEY,
            done_at  timestamptz NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    for table in ("migrations_done", "draft_usage", "fires", "rule_checks", "rules", "events", "event_types"):
        op.execute(f"DROP TABLE IF EXISTS {table}")
