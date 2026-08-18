"""How a migration seeds the system prompt without overwriting what a person wrote.

Here rather than inside a migration because the next seeding migration must not write this
`WHERE` again from memory — that is exactly how the rule gets forgotten once. Imported by
migrations only; nothing in the runtime path calls it.

The rule is one sentence: **a seed lands only when the newest revision is itself a seed.**
An operator who has saved anything since the last deployment keeps their text, and the new
default is simply not applied (specs/agent-prompt-management, "Zasiew z wdrożenia nie
przykrywa tego, co zapisał operator").

An empty table counts as seedable — that is the first seed on a fresh database, and it is
the case `0003` was written for.
"""

from __future__ import annotations

import sqlalchemy as sa

_SEED = sa.text(
    """
    INSERT INTO prompt_revisions (version, with_tools_body, without_tools_body, source)
    SELECT :version, :with_tools, :without_tools, 'seed'
     WHERE NOT EXISTS (SELECT 1 FROM prompt_revisions)
        OR (SELECT source FROM prompt_revisions ORDER BY id DESC LIMIT 1) = 'seed'
    """
)


def seed_prompt(connection, *, version: str, with_tools: str, without_tools: str) -> bool:
    """Insert this seed unless the operator has written since the last one.

    Returns whether it went in, so a migration can log the skip rather than leave the
    operator wondering why a deployment's prompt change did not appear.
    """
    result = connection.execute(
        _SEED, {"version": version, "with_tools": with_tools, "without_tools": without_tools}
    )
    return result.rowcount > 0
