"""The machine a schedule and a trigger both are, and everything that follows from being that machine. The
owner is copied at creation rather than reached through the team: an access check must not depend on a join.

Every "claim" statement is a conditional UPDATE whose WHERE clause is the whole of the exactly-once
guarantee: a second caller waits on Postgres's own row lock, re-evaluates, and finds the row no longer due.
No advisory lock, no leader process, nothing that outlives one statement."""

from __future__ import annotations


class _Recurring:
    """The statements a schedule and a trigger hold in common, written once per table. The two are the same
    machine pointed at different questions, and only the table, the column list and the "due" column differ.

    Written as one statement per rule rather than two copies, because the rules are the load-bearing part
    and a copy only has to drift once. What is deliberately not here is what genuinely differs."""

    def __init__(self, *, table: str, columns: str, due_column: str, fire_column: str) -> None:
        self.select = f"""
            SELECT {columns} FROM {table} WHERE id = $1 AND owner_principal = $2
        """

        self.select_for_team = f"""
            SELECT {columns} FROM {table}
             WHERE team_id = $1 AND owner_principal = $2
             ORDER BY created_at DESC, id DESC
        """

        # Re-enabling clears whatever disabled it and gives it a clean run of failures. Disabling by an
        # operator's own choice leaves the reason as it was: they need no explanation of their own decision.
        self.set_enabled = f"""
            UPDATE {table}
               SET enabled = $3,
                   disabled_reason = CASE WHEN $3 THEN NULL ELSE disabled_reason END,
                   consecutive_failures = CASE WHEN $3 THEN 0 ELSE consecutive_failures END,
                   updated_at = now()
             WHERE id = $1 AND owner_principal = $2
            RETURNING {columns}
        """

        # The owner rides in the WHERE rather than being checked after the read, so "not yours" and "not
        # there" are one statement and one answer.
        self.delete = f"""
            DELETE FROM {table} WHERE id = $1 AND owner_principal = $2 RETURNING id
        """

        # System-initiated — no owner filter, because the caller is the clock loop acting on a row it
        # already resolved, not an operator's request.
        self.disable_for_failures = f"""
            UPDATE {table} SET enabled = false, disabled_reason = $2, updated_at = now()
             WHERE id = $1
            RETURNING {columns}
        """

        self.increment_failures = f"""
            UPDATE {table}
               SET consecutive_failures = consecutive_failures + 1, updated_at = now()
             WHERE id = $1
            RETURNING {columns}
        """

        self.reset_failures = f"""
            UPDATE {table} SET consecutive_failures = 0, updated_at = now()
             WHERE id = $1
            RETURNING {columns}
        """

        self.claim_due = f"""
            UPDATE {table} SET {due_column} = $2, updated_at = now()
             WHERE id = $1 AND enabled AND {due_column} <= now()
            RETURNING {columns}
        """

        # No owner filter — the clock works across every operator's rows at once, the one place that
        # legitimately does. `enabled` rides in the WHERE so the partial index answers this, not a scan.
        self.select_due = f"""
            SELECT {columns} FROM {table} WHERE enabled AND {due_column} <= now()
        """

        self.select_fires = f"""
            SELECT f.id, f.schedule_id, f.trigger_id, f.fired_at, f.outcome, f.reason,
                   f.run_id, f.skipped_count
              FROM schedule_fires f
              JOIN {table} o ON o.id = f.{fire_column}
             WHERE f.{fire_column} = $1 AND o.owner_principal = $2
             ORDER BY f.fired_at DESC, f.id DESC
        """

        # `runs` carries no `schedule_id` — the fire that started a run is the only record of which run
        # belongs to which, so "is the previous run still working" walks back to the most recent fire.
        self.latest_run_status = f"""
            SELECT r.status
              FROM schedule_fires f
              JOIN runs r ON r.id = f.run_id
             WHERE f.{fire_column} = $1 AND f.outcome = 'started'
             ORDER BY f.fired_at DESC
             LIMIT 1
        """


SCHEDULE_COLUMNS = """
    id, team_id, owner_principal, revision_mode, pinned_revision_id, cron_expression,
    next_fire_at, enabled, disabled_reason, consecutive_failures,
    created_at, updated_at
"""

TRIGGER_COLUMNS = """
    id, team_id, owner_principal, revision_mode, pinned_revision_id, tool_name,
    arguments, field_path, comparison, threshold, cooldown_seconds,
    poll_interval_seconds, next_check_at, last_result, last_checked_at, last_fired_at,
    enabled, disabled_reason, consecutive_failures, created_at, updated_at
"""

SCHEDULES = _Recurring(
    table="schedules",
    columns=SCHEDULE_COLUMNS,
    due_column="next_fire_at",
    fire_column="schedule_id",
)

TRIGGERS = _Recurring(
    table="triggers",
    columns=TRIGGER_COLUMNS,
    due_column="next_check_at",
    fire_column="trigger_id",
)
