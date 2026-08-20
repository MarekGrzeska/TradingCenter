"""The machine a schedule and a trigger both are, and everything that follows from being
that machine.

`schedules.owner_principal` and `triggers.owner_principal` are copied at creation rather
than reached through the team they point at — the same reasoning `runs.owner_principal`
carries in `runs.py`: an access check MUST NOT depend on a join, and a row survives its team
being retired (specs/teams-schedules, "Harmonogram należy do operatora, który go zapisał").

Every "claim" statement here is a conditional UPDATE whose WHERE clause is the whole of the
exactly-once guarantee (design.md, "Wyzwolenie przejmowane w bazie, nie posiadane przez
proces"): a second caller's UPDATE waits on Postgres's own row lock, then re-evaluates the
same WHERE against the row the first caller already advanced — and finds it no longer due.
No advisory lock, no "leader" process, nothing that outlives one statement.

`SCHEDULES` and `TRIGGERS` are the two instances; `schedules.py`, `triggers.py` and
`fires.py` hold what each of them does *not* share.
"""

from __future__ import annotations


class _Recurring:
    """The statements a schedule and a trigger hold in common, written once per table.

    The two tables are the same machine pointed at different questions — a clock or a
    condition — and everything that follows from being that machine is identical in both:
    who owns the row, whether it is enabled, how many times in a row it has failed, and
    the conditional UPDATE that claims its next turn. Only the table name, the column
    list and the name of the "due" column differ, and those are what this class carries.

    Written as one statement per rule rather than two copies of each because the rules
    are the load-bearing part and a copy only has to drift once: `set_enabled` decides
    what re-enabling clears, `delete` decides that "not yours" and "not there" are one
    answer, and `claim` is the whole of the exactly-once guarantee. Each of those was
    true twice and had to stay true twice.

    What is deliberately *not* here is what genuinely differs: the INSERT and UPDATE
    column lists, which have nothing in common beyond `team_id`, and
    `record_trigger_check`, which only one of the two has at all.
    """

    def __init__(self, *, table: str, columns: str, due_column: str, fire_column: str) -> None:
        self.select = f"""
            SELECT {columns} FROM {table} WHERE id = $1 AND owner_principal = $2
        """

        self.select_for_team = f"""
            SELECT {columns} FROM {table}
             WHERE team_id = $1 AND owner_principal = $2
             ORDER BY created_at DESC, id DESC
        """

        # Re-enabling clears whatever disabled it and gives it a clean run of failures —
        # the same "włączyć z powrotem" specs/teams-schedules describes. Disabling by an
        # operator's own choice leaves `disabled_reason` as it was (usually NULL): the
        # operator needs no explanation of a decision they just made themselves.
        self.set_enabled = f"""
            UPDATE {table}
               SET enabled = $3,
                   disabled_reason = CASE WHEN $3 THEN NULL ELSE disabled_reason END,
                   consecutive_failures = CASE WHEN $3 THEN 0 ELSE consecutive_failures END,
                   updated_at = now()
             WHERE id = $1 AND owner_principal = $2
            RETURNING {columns}
        """

        # The owner rides in the WHERE rather than being checked after the read, so "not
        # yours" and "not there" are one statement and one answer — a route that could
        # tell them apart would be telling a stranger that the row exists.
        self.delete = f"""
            DELETE FROM {table} WHERE id = $1 AND owner_principal = $2 RETURNING id
        """

        # System-initiated — no owner filter, because the caller is the clock loop acting
        # on a row it already resolved, not an operator's request (specs/teams-schedules,
        # "Harmonogram po serii nieudanych przebiegów wyłącza się sam").
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

        # No owner filter — the clock (`scheduler/`) works across every operator's rows
        # at once, the one place in this module that legitimately does. `enabled` rides in
        # the WHERE rather than being filtered in Python so the partial index on
        # `({due_column}) WHERE enabled` is what answers this, not a table scan.
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

        # `runs` carries no `schedule_id`/`trigger_id` (design.md, "Trzy nowe tabele, zero
        # zmian w tabelach fazy 1") — the fire that started a run is the only record of
        # which run belongs to which schedule or trigger, so "is the previous run of this
        # one still working" is answered by walking back to the most recent `started` fire
        # and reading the status of the run it names, not by a join `runs` could offer.
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
