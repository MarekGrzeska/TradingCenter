"""How a migration seeds the system prompt without overwriting what a person wrote. Here rather than
inside a migration, because the next seeding migration must not write this `WHERE` again from memory.

The rule is one sentence: a seed lands only when the newest revision is itself a seed. An empty table
counts as seedable, which is the first seed on a fresh database."""

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
    """Insert this seed unless the operator has written since the last one. Returns whether it went in, so
    a migration can log the skip rather than leave the operator wondering."""
    result = connection.execute(
        _SEED, {"version": version, "with_tools": with_tools, "without_tools": without_tools}
    )
    return result.rowcount > 0
